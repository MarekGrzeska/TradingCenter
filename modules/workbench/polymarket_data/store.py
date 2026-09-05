"""Every statement this module runs against its own database. Plain asyncpg, no ORM: the tables are
handwritten SQL and so are the queries, so a read is the statement it will actually run."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from tc_runtime.db import Conn, fetch_one

from .models import CollectedRange, Event, Group, Market, Outcome, Sample, Surface


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



async def upsert_event(
    conn: Conn, event: Event, *, group_id: int | None = None
) -> int:
    """The event with its whole structure, in one transaction — all of it or none. Markets and outcomes
    are upserted rather than replaced: replacing them would cascade away the history being refreshed.

    Three statements whatever the event's size, not one per row. A measured event of 128 markets took 385
    round trips a minute here, each holding the pooled connection a read was queued behind.
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
                refreshed_at = now()
            RETURNING id
            """,
            event.provider_event_id,
            event.slug,
            event.title,
            group_id,
        )
        event_id = row["id"]
        if not event.markets:
            return event_id

        # Last of each duplicate wins, and the order the provider sent them is kept. Two rows with one
        # conflict target in a single statement is an error, not a last-write-wins, so this is required.
        markets = list({market.provider_market_id: market for market in event.markets}.values())
        market_rows = await conn.fetch(
            """
            INSERT INTO markets (
                event_id, provider_market_id, condition_id, question,
                group_item_title, neg_risk, closed, resolved_outcome, updated_at
            )
            SELECT $1, m.provider_market_id, m.condition_id, m.question,
                   m.group_item_title, m.neg_risk, m.closed, m.resolved_outcome, now()
            FROM unnest(
                $2::text[], $3::text[], $4::text[], $5::text[], $6::bool[], $7::bool[], $8::text[]
            ) AS m(
                provider_market_id, condition_id, question,
                group_item_title, neg_risk, closed, resolved_outcome
            )
            ON CONFLICT (provider_market_id) DO UPDATE SET
                event_id = EXCLUDED.event_id,
                condition_id = EXCLUDED.condition_id,
                question = EXCLUDED.question,
                group_item_title = EXCLUDED.group_item_title,
                neg_risk = EXCLUDED.neg_risk,
                closed = EXCLUDED.closed,
                resolved_outcome = EXCLUDED.resolved_outcome,
                updated_at = now()
            RETURNING id, provider_market_id
            """,
            event_id,
            [market.provider_market_id for market in markets],
            [market.condition_id for market in markets],
            [market.question for market in markets],
            [market.group_item_title for market in markets],
            [market.neg_risk for market in markets],
            [market.closed for market in markets],
            [market.resolved_outcome for market in markets],
        )
        market_ids = {row["provider_market_id"]: row["id"] for row in market_rows}

        outcomes = {
            outcome.token_id: (market_ids[market.provider_market_id], outcome)
            for market in markets
            for outcome in market.outcomes
        }
        if not outcomes:
            return event_id
        await conn.execute(
            """
            INSERT INTO outcomes (market_id, position, name, token_id)
            SELECT * FROM unnest($1::bigint[], $2::int[], $3::text[], $4::text[])
            ON CONFLICT (token_id) DO UPDATE SET
                market_id = EXCLUDED.market_id,
                position = EXCLUDED.position,
                name = EXCLUDED.name
            """,
            [market_id for market_id, _ in outcomes.values()],
            [outcome.position for _, outcome in outcomes.values()],
            [outcome.name for _, outcome in outcomes.values()],
            list(outcomes),
        )
    return event_id


async def load_events(
    conn: Conn,
    *,
    group_id: int | None = None,
    provider_event_id: str | None = None,
) -> list[Event]:
    """Every tracked event with its markets and outcomes, in three queries rather than
    N+1 — an event of 128 markets is a measured shape, not a hypothetical one."""
    events = await conn.fetch(
        """
        SELECT e.id, e.provider_event_id, e.slug, e.title, e.group_id, g.name AS group_name,
               e.tracked_at, e.refreshed_at
        FROM tracked_events e
        LEFT JOIN observation_groups g ON g.id = e.group_id
        WHERE ($1::bigint IS NULL OR e.group_id = $1)
          AND ($2::text IS NULL OR e.provider_event_id = $2)
        ORDER BY e.tracked_at, e.id
        """,
        group_id,
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
            refreshed_at=row["refreshed_at"],
            markets=tuple(by_event.get(row["id"], ())),
        )
        for row in events
    ]


async def count_tracked(conn: Conn) -> int:
    """Events under observation right now. The ceiling counts these, not markets — one
    provider request covers an event however many markets hang off it."""
    return await conn.fetchval("SELECT count(*) FROM tracked_events") or 0


async def remove_event(conn: Conn, provider_event_id: str) -> bool:
    """The observation and everything collected for it. One statement, and the atomicity is the schema's:
    five tables cascade from this row, so there is no order to get wrong and no half-done state."""
    result = await conn.execute(
        "DELETE FROM tracked_events WHERE provider_event_id = $1", provider_event_id
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
        WHERE m.resolved_outcome IS NULL
        ORDER BY e.id, m.id, o.position
        """
    )
    return [(row["id"], row["token_id"], row["event_id"]) for row in rows]



async def record_samples(conn: Conn, samples: list[Sample]) -> int:
    """Upsert on `(outcome_id, observed_at)`: the sampler and a backfill meet in the same minute
    regularly. The later write wins only on the columns it carries, so a backfill erases no last trade."""
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


async def latest_samples(conn: Conn) -> dict[int, Sample]:
    """The newest sample of every tracked outcome, in one query — the snapshot the terminal opens on.
    A request per event would be a request per row of the screen.

    Driven from `outcomes` with a LATERAL rather than `DISTINCT ON` over the samples, so the cost follows
    the number of outcomes and not the depth of the archive. `DISTINCT ON (outcome_id) ORDER BY
    outcome_id, observed_at DESC` matches no index this schema can hold — the two columns are wanted in
    opposite directions — so it sorted every sample ever collected: 3,5 s at 3,2M rows, measured
    31 August 2026, on a read the two screens make every 30 s.
    """
    rows = await conn.fetch(
        """
        SELECT s.outcome_id, s.observed_at, s.midpoint, s.last_trade, s.quoted_at, s.source
        FROM outcomes o
        JOIN LATERAL (
            SELECT p.outcome_id, p.observed_at, p.midpoint, p.last_trade, p.quoted_at, p.source
            FROM price_samples p
            WHERE p.outcome_id = o.id
            ORDER BY p.observed_at DESC
            LIMIT 1
        ) s ON true
        """
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
    """The base point a change window is measured from. At or *before*, and the caller decides whether
    it is close enough: the provider's spacing wobbles, so an exact instant would answer "no data"."""
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



async def record_collected(
    conn: Conn, outcome_id: int, starts_at: datetime, ends_at: datetime
) -> None:
    """Adds a window and merges it with everything it touches. Two adjacent ranges left separate answer
    "not collected" for the instant between them, which is a gap nothing ever fills."""
    await record_collected_many(conn, [outcome_id], starts_at, ends_at)


async def record_collected_many(
    conn: Conn, outcome_ids: Sequence[int], starts_at: datetime, ends_at: datetime
) -> None:
    """The same window against many outcomes, in one statement — what a tick records, since every outcome
    of an event is covered by the one interval. One statement each was a round trip per outcome per minute."""
    if not outcome_ids:
        return
    await conn.execute(
        """
        WITH incoming AS (
            SELECT DISTINCT unnest($1::bigint[]) AS outcome_id
        ),
        touching AS (
            DELETE FROM collected_ranges c
            USING incoming i
            WHERE c.outcome_id = i.outcome_id AND c.starts_at <= $3 AND c.ends_at >= $2
            RETURNING c.outcome_id, c.starts_at, c.ends_at
        )
        INSERT INTO collected_ranges (outcome_id, starts_at, ends_at)
        SELECT i.outcome_id,
               LEAST($2, COALESCE(min(t.starts_at), $2)),
               GREATEST($3, COALESCE(max(t.ends_at), $3))
        FROM incoming i
        LEFT JOIN touching t ON t.outcome_id = i.outcome_id
        GROUP BY i.outcome_id
        """,
        list(outcome_ids),
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
    """The "provider has nothing older" boundary, written at the oldest point a read actually returned —
    never the edge asked for. Only moved earlier: a later read finding less is the provider being unhelpful."""
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
    """Lifts the boundary, for the one act that means "check that again": somebody asking for data older
    than it. The provider's history deepens over time."""
    await conn.execute(
        "UPDATE outcomes SET oldest_available_at = NULL WHERE id = $1", outcome_id
    )



async def delete_history(conn: Conn, event_id: int) -> tuple[int, int]:
    """Samples and collected ranges together, or neither. A range surviving its samples is binding on
    planning, so the window would read as collected and backfill would never return to it."""
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



async def sampleable_events(conn: Conn) -> list[tuple[int, str]]:
    """`(event_id, provider_event_id)` for every event still worth a request. The unit is the event
    because the request is: one read prices every outcome of every market it holds."""
    rows = await conn.fetch(
        """
        SELECT DISTINCT e.id, e.provider_event_id
        FROM tracked_events e
        JOIN markets m ON m.event_id = e.id
        WHERE m.resolved_outcome IS NULL
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
    """Counted rather than merely logged. Repeated failure is what the list of observations has to be
    able to say out loud — silence in the data must not read as silence in the market."""
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


async def newest_sample_at(conn: Conn, event_id: int) -> dict[int, datetime]:
    """Where a gap-closing read has to start from, for every unresolved outcome of one event.

    One statement rather than one per outcome: a restart asks this of every event it tracks, and a
    measured event holds 256 outcomes. An outcome with nothing collected is absent, not `None`.
    """
    rows = await conn.fetch(
        """
        SELECT o.id, s.observed_at
        FROM outcomes o
        JOIN markets m ON m.id = o.market_id
        JOIN LATERAL (
            SELECT p.observed_at FROM price_samples p
            WHERE p.outcome_id = o.id
            ORDER BY p.observed_at DESC
            LIMIT 1
        ) s ON true
        WHERE m.event_id = $1 AND m.resolved_outcome IS NULL
        """,
        event_id,
    )
    return {row["id"]: row["observed_at"] for row in rows}
