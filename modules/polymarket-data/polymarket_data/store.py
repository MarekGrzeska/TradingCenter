"""Every statement this module runs against its own database.

Plain asyncpg, no ORM: the tables are handwritten SQL in the migrations and the queries are
handwritten here, so a read is the statement it will actually run.
"""

from __future__ import annotations

from datetime import datetime

from tc_runtime.db import Conn, fetch_one

from .models import CollectedRange, Event, Group, Market, Outcome, Sample, Surface

# --- groups ---------------------------------------------------------------------------


async def create_group(conn: Conn, name: str) -> Group:
    """Idempotent on the name: asking twice for the same category is not an error, and a
    model that asks again after a restart should not have to know whether it asked before."""
    row = await fetch_one(
        conn,
        """
        INSERT INTO observation_groups (name) VALUES ($1)
        ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
        RETURNING id, name
        """,
        name,
    )
    return Group(id=row["id"], name=row["name"])


async def list_groups(conn: Conn) -> list[Group]:
    rows = await conn.fetch(
        """
        SELECT g.id, g.name,
               COALESCE(array_agg(e.id) FILTER (WHERE e.id IS NOT NULL), '{}') AS event_ids
        FROM observation_groups g
        LEFT JOIN tracked_events e ON e.group_id = g.id
        GROUP BY g.id, g.name
        ORDER BY g.name
        """
    )
    return [
        Group(id=row["id"], name=row["name"], event_ids=tuple(row["event_ids"])) for row in rows
    ]


async def delete_group(conn: Conn, group_id: int) -> bool:
    """The events keep their observation and every sample — `group_id` is `ON DELETE SET
    NULL`, so they come back ungrouped rather than untracked."""
    result = await conn.execute("DELETE FROM observation_groups WHERE id = $1", group_id)
    return result.endswith(" 1")


async def assign_group(conn: Conn, event_id: int, group_id: int | None) -> bool:
    result = await conn.execute(
        "UPDATE tracked_events SET group_id = $2 WHERE id = $1", event_id, group_id
    )
    return result.endswith(" 1")


# --- events, markets, outcomes ----------------------------------------------------------


async def upsert_event(conn: Conn, event: Event, *, group_id: int | None = None) -> int:
    """The event with its whole structure, in one transaction.

    All of it or none of it: an event row without its markets is an observation the sampler
    would run against nothing, and a market without its outcomes has no token to ask about.

    Markets and outcomes are upserted rather than replaced. Replacing them would take every
    outcome's id with it and `price_samples` cascades from those ids — a refresh would then
    delete the history it was refreshing. The provider adding a market to a running event is
    a measured case, so this path is walked often, not only at first track.
    """
    async with conn.transaction():
        row = await fetch_one(
            conn,
            """
            INSERT INTO tracked_events (provider_event_id, slug, title, group_id, refreshed_at)
            VALUES ($1, $2, $3, $4, now())
            ON CONFLICT (provider_event_id) DO UPDATE SET
                slug = EXCLUDED.slug,
                title = EXCLUDED.title,
                group_id = COALESCE(EXCLUDED.group_id, tracked_events.group_id),
                refreshed_at = now(),
                -- Tracking the same event again resumes it. The history stayed, so this
                -- continues a series rather than starting one.
                tracking_ended_at = NULL
            RETURNING id
            """,
            event.provider_event_id,
            event.slug,
            event.title,
            group_id,
        )
        event_id = row["id"]

        for market in event.markets:
            market_row = await fetch_one(
                conn,
                """
                INSERT INTO markets (
                    event_id, provider_market_id, condition_id, question,
                    group_item_title, neg_risk, closed, resolved_outcome, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, now())
                ON CONFLICT (provider_market_id) DO UPDATE SET
                    event_id = EXCLUDED.event_id,
                    condition_id = EXCLUDED.condition_id,
                    question = EXCLUDED.question,
                    group_item_title = EXCLUDED.group_item_title,
                    neg_risk = EXCLUDED.neg_risk,
                    closed = EXCLUDED.closed,
                    resolved_outcome = EXCLUDED.resolved_outcome,
                    updated_at = now()
                RETURNING id
                """,
                event_id,
                market.provider_market_id,
                market.condition_id,
                market.question,
                market.group_item_title,
                market.neg_risk,
                market.closed,
                market.resolved_outcome,
            )
            market_id = market_row["id"]

            for outcome in market.outcomes:
                await conn.execute(
                    """
                    INSERT INTO outcomes (market_id, position, name, token_id)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (token_id) DO UPDATE SET
                        market_id = EXCLUDED.market_id,
                        position = EXCLUDED.position,
                        name = EXCLUDED.name
                    """,
                    market_id,
                    outcome.position,
                    outcome.name,
                    outcome.token_id,
                )
    return event_id


async def load_events(
    conn: Conn,
    *,
    group_id: int | None = None,
    include_ended: bool = True,
    provider_event_id: str | None = None,
) -> list[Event]:
    """Every tracked event with its markets and outcomes, in three queries rather than
    N+1 — an event of 128 markets is a measured shape, not a hypothetical one."""
    events = await conn.fetch(
        """
        SELECT e.id, e.provider_event_id, e.slug, e.title, e.group_id, g.name AS group_name,
               e.tracked_at, e.tracking_ended_at, e.refreshed_at
        FROM tracked_events e
        LEFT JOIN observation_groups g ON g.id = e.group_id
        WHERE ($1::bigint IS NULL OR e.group_id = $1)
          AND ($2::boolean OR e.tracking_ended_at IS NULL)
          AND ($3::text IS NULL OR e.provider_event_id = $3)
        ORDER BY e.tracked_at, e.id
        """,
        group_id,
        include_ended,
        provider_event_id,
    )
    if not events:
        return []

    ids = [row["id"] for row in events]
    markets = await conn.fetch(
        """
        SELECT id, event_id, provider_market_id, condition_id, question, group_item_title,
               neg_risk, closed, resolved_outcome
        FROM markets WHERE event_id = ANY($1::bigint[]) ORDER BY id
        """,
        ids,
    )
    outcomes = await conn.fetch(
        """
        SELECT o.id, o.market_id, o.position, o.name, o.token_id, o.oldest_available_at
        FROM outcomes o
        JOIN markets m ON m.id = o.market_id
        WHERE m.event_id = ANY($1::bigint[])
        ORDER BY o.market_id, o.position
        """,
        ids,
    )

    by_market: dict[int, list[Outcome]] = {}
    for row in outcomes:
        by_market.setdefault(row["market_id"], []).append(
            Outcome(
                id=row["id"],
                position=row["position"],
                name=row["name"],
                token_id=row["token_id"],
                oldest_available_at=row["oldest_available_at"],
            )
        )

    by_event: dict[int, list[Market]] = {}
    for row in markets:
        by_event.setdefault(row["event_id"], []).append(
            Market(
                id=row["id"],
                provider_market_id=row["provider_market_id"],
                condition_id=row["condition_id"],
                question=row["question"],
                group_item_title=row["group_item_title"],
                neg_risk=row["neg_risk"],
                closed=row["closed"],
                resolved_outcome=row["resolved_outcome"],
                outcomes=tuple(by_market.get(row["id"], ())),
            )
        )

    return [
        Event(
            id=row["id"],
            provider_event_id=row["provider_event_id"],
            slug=row["slug"],
            title=row["title"],
            group_id=row["group_id"],
            group_name=row["group_name"],
            tracked_at=row["tracked_at"],
            tracking_ended_at=row["tracking_ended_at"],
            refreshed_at=row["refreshed_at"],
            markets=tuple(by_event.get(row["id"], ())),
        )
        for row in events
    ]


async def count_tracked(conn: Conn) -> int:
    """Events under observation right now. The ceiling counts these, not markets — one
    provider request covers an event however many markets hang off it."""
    return (
        await conn.fetchval(
            "SELECT count(*) FROM tracked_events WHERE tracking_ended_at IS NULL"
        )
        or 0
    )


async def end_tracking(conn: Conn, provider_event_id: str) -> bool:
    """Stops the sampling. Touches not one sample — deleting history is a separate act, on
    a different surface, and no tool can reach it."""
    result = await conn.execute(
        """
        UPDATE tracked_events SET tracking_ended_at = now()
        WHERE provider_event_id = $1 AND tracking_ended_at IS NULL
        """,
        provider_event_id,
    )
    return result.endswith(" 1")


async def mark_resolved(conn: Conn, provider_market_id: str, winning_outcome: str) -> bool:
    """The provider has answered this market. Sampling stops for it; its history stays, and
    the event stays on the list marked rather than disappearing from it."""
    result = await conn.execute(
        """
        UPDATE markets SET resolved_outcome = $2, closed = true, updated_at = now()
        WHERE provider_market_id = $1
        """,
        provider_market_id,
        winning_outcome,
    )
    return result.endswith(" 1")


async def sampleable_outcomes(conn: Conn) -> list[tuple[int, str, int]]:
    """`(outcome_id, token_id, event_id)` for every outcome the sampler should still ask
    about: tracked event, unresolved market."""
    rows = await conn.fetch(
        """
        SELECT o.id, o.token_id, e.id AS event_id
        FROM outcomes o
        JOIN markets m ON m.id = o.market_id
        JOIN tracked_events e ON e.id = m.event_id
        WHERE e.tracking_ended_at IS NULL AND m.resolved_outcome IS NULL
        ORDER BY e.id, m.id, o.position
        """
    )
    return [(row["id"], row["token_id"], row["event_id"]) for row in rows]


# --- samples ---------------------------------------------------------------------------


async def record_samples(conn: Conn, samples: list[Sample]) -> int:
    """Upsert on `(outcome_id, observed_at)`.

    The sampler and a backfill meet in the same minute regularly, and two rows for one
    moment would leave a series with two prices at one instant. The later write wins on the
    columns it carries and leaves the others alone, so a backfill carrying only a midpoint
    does not erase a last trade the sampler wrote for the same moment.
    """
    if not samples:
        return 0
    await conn.executemany(
        """
        INSERT INTO price_samples (
            outcome_id, observed_at, midpoint, last_trade, quoted_at, source
        )
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (outcome_id, observed_at) DO UPDATE SET
            midpoint = COALESCE(EXCLUDED.midpoint, price_samples.midpoint),
            last_trade = COALESCE(EXCLUDED.last_trade, price_samples.last_trade),
            quoted_at = COALESCE(EXCLUDED.quoted_at, price_samples.quoted_at),
            source = EXCLUDED.source
        """,
        [
            (
                sample.outcome_id,
                sample.observed_at,
                sample.midpoint,
                sample.last_trade,
                sample.quoted_at,
                sample.source.value,
            )
            for sample in samples
        ],
    )
    return len(samples)


async def history(
    conn: Conn, outcome_id: int, *, since: datetime, until: datetime
) -> list[Sample]:
    """One outcome's series, oldest first — the order every chart and every window
    computation reads it in."""
    rows = await conn.fetch(
        """
        SELECT outcome_id, observed_at, midpoint, last_trade, quoted_at, source
        FROM price_samples
        WHERE outcome_id = $1 AND observed_at >= $2 AND observed_at <= $3
        ORDER BY observed_at
        """,
        outcome_id,
        since,
        until,
    )
    return [
        Sample(
            outcome_id=row["outcome_id"],
            observed_at=row["observed_at"],
            midpoint=row["midpoint"],
            last_trade=row["last_trade"],
            quoted_at=row["quoted_at"],
            source=Surface(row["source"]),
        )
        for row in rows
    ]


async def latest_samples(conn: Conn, *, include_ended: bool = False) -> dict[int, Sample]:
    """The newest sample of every tracked outcome, in one query.

    The snapshot the terminal opens on. A request per event would be a request per row of
    the screen, and one measured event holds 128 markets.
    """
    rows = await conn.fetch(
        """
        SELECT DISTINCT ON (s.outcome_id)
               s.outcome_id, s.observed_at, s.midpoint, s.last_trade, s.quoted_at, s.source
        FROM price_samples s
        JOIN outcomes o ON o.id = s.outcome_id
        JOIN markets m ON m.id = o.market_id
        JOIN tracked_events e ON e.id = m.event_id
        WHERE ($1::boolean OR e.tracking_ended_at IS NULL)
        ORDER BY s.outcome_id, s.observed_at DESC
        """,
        include_ended,
    )
    return {
        row["outcome_id"]: Sample(
            outcome_id=row["outcome_id"],
            observed_at=row["observed_at"],
            midpoint=row["midpoint"],
            last_trade=row["last_trade"],
            quoted_at=row["quoted_at"],
            source=Surface(row["source"]),
        )
        for row in rows
    }


async def sample_at_or_before(conn: Conn, outcome_id: int, moment: datetime) -> Sample | None:
    """The base point a change window is measured from.

    At or *before*, and the caller decides whether what comes back is close enough — the
    provider's own spacing wobbles between 57 and 63 seconds and widens on its own for older
    ranges, so a window that demanded an exact instant would answer "no data" on a series
    that plainly has some.
    """
    row = await conn.fetchrow(
        """
        SELECT outcome_id, observed_at, midpoint, last_trade, quoted_at, source
        FROM price_samples
        WHERE outcome_id = $1 AND observed_at <= $2
        ORDER BY observed_at DESC
        LIMIT 1
        """,
        outcome_id,
        moment,
    )
    if row is None:
        return None
    return Sample(
        outcome_id=row["outcome_id"],
        observed_at=row["observed_at"],
        midpoint=row["midpoint"],
        last_trade=row["last_trade"],
        quoted_at=row["quoted_at"],
        source=Surface(row["source"]),
    )


# --- what has actually been collected ----------------------------------------------------


async def record_collected(
    conn: Conn, outcome_id: int, starts_at: datetime, ends_at: datetime
) -> None:
    """Adds a window and merges it with everything it touches, in one statement.

    Merging matters more than tidiness: two adjacent ranges left separate answer "not
    collected" for the instant between them, which is a gap this module would then keep
    trying to fill for ever.
    """
    await conn.execute(
        """
        WITH touching AS (
            DELETE FROM collected_ranges
            WHERE outcome_id = $1 AND starts_at <= $3 AND ends_at >= $2
            RETURNING starts_at, ends_at
        )
        INSERT INTO collected_ranges (outcome_id, starts_at, ends_at)
        SELECT $1,
               LEAST($2, COALESCE(min(starts_at), $2)),
               GREATEST($3, COALESCE(max(ends_at), $3))
        FROM touching
        """,
        outcome_id,
        starts_at,
        ends_at,
    )


async def collected_ranges(conn: Conn, outcome_id: int) -> list[CollectedRange]:
    rows = await conn.fetch(
        "SELECT starts_at, ends_at FROM collected_ranges WHERE outcome_id = $1 "
        "ORDER BY starts_at",
        outcome_id,
    )
    return [CollectedRange(starts_at=row["starts_at"], ends_at=row["ends_at"]) for row in rows]


async def is_collected(conn: Conn, outcome_id: int, moment: datetime) -> bool:
    """Whether the absence of a sample at this moment means "nobody traded" or "we were not
    looking". Without this record the two are the same absence."""
    return bool(
        await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM collected_ranges
                WHERE outcome_id = $1 AND starts_at <= $2 AND ends_at >= $2
            )
            """,
            outcome_id,
            moment,
        )
    )


async def note_oldest_available(conn: Conn, outcome_id: int, moment: datetime) -> None:
    """The "the provider has nothing older" boundary, written at the oldest point a read
    actually returned.

    Never at the edge of the window asked for: those two are separated by everything the
    provider did not have, and writing the second announces as checked something nobody
    checked. Only moved *earlier* — a later read finding less is the provider being
    unhelpful, not history shrinking.
    """
    await conn.execute(
        """
        UPDATE outcomes
        SET oldest_available_at = LEAST($2, COALESCE(oldest_available_at, $2))
        WHERE id = $1
        """,
        outcome_id,
        moment,
    )


async def clear_oldest_available(conn: Conn, outcome_id: int) -> None:
    """Lifts the boundary, for the one act that means "check that again": somebody asking
    for data older than it. The provider's history deepens over time and the record may have
    come from an answer that did not mean what was read into it."""
    await conn.execute(
        "UPDATE outcomes SET oldest_available_at = NULL WHERE id = $1", outcome_id
    )


# --- deletion, the one act nobody can undo ------------------------------------------------


async def delete_history(conn: Conn, event_id: int) -> tuple[int, int]:
    """Samples and collected ranges together, or neither. Returns `(samples, ranges)`.

    A range surviving its samples is worse than either alone: it is binding on planning, so
    the window would read as already collected and backfill would never return to it.

    The event, its markets and its outcomes stay. What is deleted is the collected data, not
    the observation — ending an observation is a different act again.
    """
    async with conn.transaction():
        samples = await conn.fetchval(
            """
            WITH gone AS (
                DELETE FROM price_samples
                WHERE outcome_id IN (
                    SELECT o.id FROM outcomes o
                    JOIN markets m ON m.id = o.market_id
                    WHERE m.event_id = $1
                )
                RETURNING 1
            )
            SELECT count(*) FROM gone
            """,
            event_id,
        )
        ranges = await conn.fetchval(
            """
            WITH gone AS (
                DELETE FROM collected_ranges
                WHERE outcome_id IN (
                    SELECT o.id FROM outcomes o
                    JOIN markets m ON m.id = o.market_id
                    WHERE m.event_id = $1
                )
                RETURNING 1
            )
            SELECT count(*) FROM gone
            """,
            event_id,
        )
        await conn.execute(
            """
            UPDATE outcomes SET oldest_available_at = NULL
            WHERE market_id IN (SELECT id FROM markets WHERE event_id = $1)
            """,
            event_id,
        )
    return int(samples or 0), int(ranges or 0)


# --- what collection is currently doing ---------------------------------------------------


async def sampleable_events(conn: Conn) -> list[tuple[int, str]]:
    """`(event_id, provider_event_id)` for every event still worth a request: tracked, and
    holding at least one market the provider has not answered.

    The unit is the event because the request is: one read of the metadata surface prices
    every outcome of every market it holds.
    """
    rows = await conn.fetch(
        """
        SELECT DISTINCT e.id, e.provider_event_id
        FROM tracked_events e
        JOIN markets m ON m.event_id = e.id
        WHERE e.tracking_ended_at IS NULL AND m.resolved_outcome IS NULL
        ORDER BY e.id
        """
    )
    return [(row["id"], row["provider_event_id"]) for row in rows]


async def outcome_ids_by_token(conn: Conn, event_id: int) -> dict[str, int]:
    """The provider speaks in tokens and this archive in outcome ids. One lookup per event
    rather than per outcome, because one measured event holds 256 of them."""
    rows = await conn.fetch(
        """
        SELECT o.token_id, o.id
        FROM outcomes o JOIN markets m ON m.id = o.market_id
        WHERE m.event_id = $1
        """,
        event_id,
    )
    return {row["token_id"]: row["id"] for row in rows}


async def note_sampled(conn: Conn, event_id: int) -> None:
    await conn.execute(
        """
        INSERT INTO sampling_state (event_id, last_success_at, consecutive_failures)
        VALUES ($1, now(), 0)
        ON CONFLICT (event_id) DO UPDATE SET
            last_success_at = now(),
            consecutive_failures = 0,
            last_failure_reason = NULL
        """,
        event_id,
    )


async def note_sampling_failed(conn: Conn, event_id: int, reason: str) -> None:
    """Counted rather than merely logged. Repeated failure is what the list of observations
    has to be able to say out loud — silence in the data must not read as silence in the
    market."""
    await conn.execute(
        """
        INSERT INTO sampling_state (
            event_id, last_failure_at, last_failure_reason, consecutive_failures
        )
        VALUES ($1, now(), $2, 1)
        ON CONFLICT (event_id) DO UPDATE SET
            last_failure_at = now(),
            last_failure_reason = $2,
            consecutive_failures = sampling_state.consecutive_failures + 1
        """,
        event_id,
        reason[:500],
    )


async def sampling_state(conn: Conn) -> dict[int, dict]:
    rows = await conn.fetch(
        "SELECT event_id, last_success_at, last_failure_at, last_failure_reason, "
        "consecutive_failures FROM sampling_state"
    )
    return {row["event_id"]: dict(row) for row in rows}


async def outcomes_of_event(conn: Conn, event_id: int) -> list[tuple[int, str, datetime | None]]:
    """`(outcome_id, token_id, oldest_available_at)` for a backfill to walk."""
    rows = await conn.fetch(
        """
        SELECT o.id, o.token_id, o.oldest_available_at
        FROM outcomes o JOIN markets m ON m.id = o.market_id
        WHERE m.event_id = $1 AND m.resolved_outcome IS NULL
        ORDER BY m.id, o.position
        """,
        event_id,
    )
    return [(row["id"], row["token_id"], row["oldest_available_at"]) for row in rows]


async def newest_sample_at(conn: Conn, outcome_id: int) -> datetime | None:
    """Where a gap-closing read has to start from."""
    return await conn.fetchval(
        "SELECT max(observed_at) FROM price_samples WHERE outcome_id = $1", outcome_id
    )
