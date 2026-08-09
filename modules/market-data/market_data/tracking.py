"""Which pairs are collected — the operator's standing decision, and how it is going.

Nothing is archived because somebody looked at a chart. Collecting a pair means holding a
provider connection open around the clock, and the provider limits how many a session may
hold, so spending one is a decision rather than a side effect of browsing. That is the
whole reason this module exists instead of a list in a configuration file: a file needs
access to the machine and a restart, and neither belongs in the loop of "archive this
too".

Untracking stops collection and keeps every candle: the row is flipped rather than
deleted, which also leaves the record of when collection stopped, and that is the gap a
later re-add has to close. An archive MUST NOT discard data on its own — not on a
configuration change, not on a restart — but an operator can ask for it directly, which
is a different, explicit operation: `deletion.py`, built on top of `untrack` here rather
than replacing it.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from enum import Enum

import asyncpg
from pydantic import BaseModel

from .errors import GatewayRefused, GatewayUnreachable
from .gateway.instruments import GatewayInstruments
from .market_status import MarketStatus
from .models import Resolution, TrackedPairState
from .periods import period_length

# How far behind the newest candle may fall before collection is called stalled. Two
# periods rather than one: a candle is only written once its period closes, so at any
# moment the newest one is legitimately up to one period old, and a threshold of one
# would call every healthy pair broken every period.
STALE_AFTER_PERIODS = 2

# Plus however long the candle takes to arrive once its period has closed, which is not
# zero and does not scale with the resolution — it is the provider sealing the candle, the
# gateway relaying it and this module storing it, and those take the same few seconds
# whether the period was a minute or a day.
#
# **Measured, because two periods alone was wrong.** Watched against the live feed on
# 2026-08-08: a closed minute candle appeared 52 to 169 seconds after its period ended, so
# a healthy `MINUTE` pair sat 112–229 seconds behind against a threshold of 120. The state
# flipped between `COLLECTING` and `STALLED` from one read to the next while nothing at all
# was wrong, which is worse than having no indicator: an operator learns to ignore it.
#
# A fixed span rather than a third period, because a third period is nothing at `MINUTE`
# and four extra hours at `HOUR_4`. Three minutes covers the slowest arrival seen with room
# to spare, and costs a genuinely dead `MINUTE` pair three minutes of extra doubt.
DELIVERY_GRACE = timedelta(minutes=3)


class TrackingRefused(Exception):
    """A pair was not taken on, and this says why.

    Refusals are named rather than returned as a bare false, because every one of them is
    something an operator has to read and act on: a symbol the provider does not know, or
    a ceiling that has to be raised deliberately.
    """


class UnknownPair(TrackingRefused):
    """The gateway could not produce a candle for this symbol at this resolution."""


class LimitReached(TrackingRefused):
    """The configured ceiling on tracked pairs is full.

    The ceiling is real: the gateway holds one provider connection per pair and the
    provider limits sessions. Refusing loudly is the point — the alternative is accepting
    the pair and quietly not collecting some of them.
    """


class CollectionState(str, Enum):
    """Whether data is actually arriving, as far as the archive can tell.

    Being on the list proves nothing. A subscription can die without a sound, and the
    only visible symptom is a series that stops growing while the market is open.
    """

    NEVER_COLLECTED = "never_collected"
    COLLECTING = "collecting"
    STALLED = "stalled"
    # Behind, but the market is shut, so there is nothing to collect and nothing wrong.
    MARKET_CLOSED = "market_closed"
    # Behind, and nobody said whether the market is open. Not reported as healthy, and
    # not reported as broken either — an honest third answer beats a confident wrong one.
    UNKNOWN = "unknown"


class TrackedPair(BaseModel):
    symbol: str
    resolution: Resolution
    state: TrackedPairState
    added_at: datetime
    untracked_at: datetime | None = None
    # The moment history for this pair is meant to reach back to — never later than the
    # value it was tracked with, even across a re-track (see `track`'s docstring).
    collect_from: datetime


class TrackedPairStatus(BaseModel):
    """A tracked pair and how its collection is going."""

    symbol: str
    resolution: Resolution
    added_at: datetime
    collect_from: datetime
    # The oldest period collected, which is how far back the data actually reaches —
    # `collect_from` is only where it was asked to reach, and a job that has not finished
    # (or a provider whose history ends later) leaves the two far apart.
    earliest_candle: datetime | None
    latest_candle: datetime | None
    collection: CollectionState


def default_collect_from(resolution: Resolution, default_bars: int, now: datetime) -> datetime:
    """Where history starts for a pair nobody gave an explicit moment for.

    The same depth a single fill without a job has always reached back to — this is
    what makes a plain `track()` call (no wizard, no job) behave exactly as it did
    before `collect_from` existed.
    """
    return now - period_length(resolution) * default_bars


# A single key rather than one per pair: the ceiling counts every tracked pair, so two
# additions racing each other have to be serialised against the same thing, not against
# their own rows. `hashtextextended` gives the bigint the advisory lock functions take.
_LOCK_TRACKING = "SELECT pg_advisory_xact_lock(hashtextextended('market_data.tracked_pairs', 0))"

_COUNT_TRACKED = "SELECT count(*) FROM tracked_pairs WHERE state = 'tracked'"

_TRACK = """
    INSERT INTO tracked_pairs (symbol, resolution, state, added_at, untracked_at, collect_from)
    VALUES ($1, $2, 'tracked', now(), NULL, $3)
    ON CONFLICT (symbol, resolution) DO UPDATE SET
        state = 'tracked',
        untracked_at = NULL,
        -- Only ever earlier, never later: re-tracking with a later moment must not
        -- abandon history the archive already committed to reaching.
        collect_from = LEAST(tracked_pairs.collect_from, EXCLUDED.collect_from)
    RETURNING symbol, resolution, state, added_at, untracked_at, collect_from
"""

_UNTRACK = """
    UPDATE tracked_pairs
       SET state = 'untracked', untracked_at = now()
     WHERE symbol = $1 AND resolution = $2 AND state = 'tracked'
    RETURNING symbol, resolution, state, added_at, untracked_at, collect_from
"""

_SELECT_TRACKED = """
    SELECT symbol, resolution, state, added_at, untracked_at, collect_from
      FROM tracked_pairs
     WHERE state = 'tracked'
     ORDER BY added_at, symbol, resolution
"""

_IS_TRACKED = """
    SELECT 1 FROM tracked_pairs
     WHERE symbol = $1 AND resolution = $2 AND state = 'tracked'
     LIMIT 1
"""

_SELECT_COLLECT_FROM = """
    SELECT collect_from FROM tracked_pairs
     WHERE symbol = $1 AND resolution = $2 AND state = 'tracked'
     LIMIT 1
"""

# One query for every tracked pair's oldest and newest candle rather than one query per
# pair. The left join keeps a pair that has never collected anything, which is a state an
# operator needs to see rather than a row that quietly goes missing.
_SELECT_STATUS = """
    SELECT t.symbol, t.resolution, t.added_at, t.collect_from,
           min(c.period_start) AS earliest_candle,
           max(c.period_start) AS latest_candle
      FROM tracked_pairs t
      LEFT JOIN candles c
        ON c.symbol = t.symbol AND c.resolution = t.resolution
     WHERE t.state = 'tracked'
     GROUP BY t.symbol, t.resolution, t.added_at, t.collect_from
     ORDER BY t.added_at, t.symbol, t.resolution
"""


def _pair(row: asyncpg.Record) -> TrackedPair:
    return TrackedPair(
        symbol=row["symbol"],
        resolution=Resolution(row["resolution"]),
        state=TrackedPairState(row["state"]),
        added_at=row["added_at"],
        untracked_at=row["untracked_at"],
        collect_from=row["collect_from"],
    )


async def track(
    conn: asyncpg.Connection,
    symbol: str,
    resolution: Resolution,
    limit: int,
    collect_from: datetime | None = None,
    default_bars: int = 5000,
) -> TrackedPair:
    """Start collecting a pair, or raise `LimitReached` saying why not.

    Re-tracking a pair that was untracked flips it back and keeps its original `added_at`,
    because it is the same standing decision resumed rather than a new one. Its candles
    were never touched, so what it needs on resumption is the gap closed, not a fresh
    start — which is what the preserved `untracked_at` was for.

    `collect_from` is the moment history should reach back to. Left unset, it is worked
    out from `default_bars` — the same depth a plain fill has always reached back to —
    so a caller that never heard of jobs or wizards gets the old behaviour unchanged.
    Re-tracking (or tracking again with an earlier moment) can only pull it earlier,
    never push it later: see `_TRACK`'s `LEAST`.
    """
    resolved_from = collect_from or default_collect_from(
        resolution, default_bars, datetime.now(UTC)
    )

    # The count and the insert have to be one atomic thing. Two additions racing each
    # other would otherwise both read `limit - 1` and both succeed, putting the archive one
    # provider connection over a ceiling that exists because the provider enforces it.
    async with conn.transaction():
        await conn.execute(_LOCK_TRACKING)

        if not await conn.fetchval(_IS_TRACKED, symbol, resolution.value):
            tracked = await conn.fetchval(_COUNT_TRACKED)
            if tracked >= limit:
                raise LimitReached(
                    f"already collecting {tracked} pairs, which is the configured ceiling "
                    f"of {limit}. The gateway holds one provider connection per pair and the "
                    f"provider limits how many a session may hold, so stop collecting a pair "
                    f"or raise MAX_TRACKED_PAIRS deliberately."
                )

        return _pair(await conn.fetchrow(_TRACK, symbol, resolution.value, resolved_from))


async def untrack(
    conn: asyncpg.Connection, symbol: str, resolution: Resolution
) -> TrackedPair | None:
    """Stop collecting a pair. Returns `None` if it was not being collected.

    The candles stay, and so does the row: the moment collection stopped is the left edge
    of the gap that tracking it again will have to close. This is the flip alone — an
    operator who wants the data gone too is `deletion.close_for_deletion`, which calls
    this and adds skipping the pair's queued chunks, both in one transaction.
    """
    row = await conn.fetchrow(_UNTRACK, symbol, resolution.value)
    return _pair(row) if row else None


async def read_tracked(conn: asyncpg.Connection) -> list[TrackedPair]:
    """Every pair currently being collected, oldest decision first.

    This is what a restart reads. There is no list in a file to disagree with it.
    """
    return [_pair(row) for row in await conn.fetch(_SELECT_TRACKED)]


async def is_tracked(conn: asyncpg.Connection, symbol: str, resolution: Resolution) -> bool:
    return await conn.fetchval(_IS_TRACKED, symbol, resolution.value) is not None


async def read_collect_from(
    conn: asyncpg.Connection, symbol: str, resolution: Resolution
) -> datetime | None:
    """The moment this pair's history is meant to reach back to, or `None` if it is not
    currently tracked.

    What the quiet gap-closing fill (`ingest/backfill.py`) reads before deciding how deep
    to reach for a pair with nothing collected yet — it MUST NOT go further back than
    this, and `None` here means there is nothing to fetch for, not "use the old default".
    """
    return await conn.fetchval(_SELECT_COLLECT_FROM, symbol, resolution.value)


def collection_state(
    resolution: Resolution,
    latest_candle: datetime | None,
    now: datetime,
    market_open: bool | None = None,
) -> CollectionState:
    """How collection is going for one pair, from the age of its newest candle.

    `market_open` is passed in rather than worked out here. Whether an instrument is
    currently tradeable is the gateway's to answer — this module has no session calendar
    and inventing one would produce a confident wrong answer twice a day.

    The threshold is two periods *plus* the time a candle takes to arrive once its period
    has closed. Both halves are load-bearing, and the second one was measured rather than
    reasoned about — see `DELIVERY_GRACE`.
    """
    if latest_candle is None:
        return CollectionState.NEVER_COLLECTED

    behind = now - latest_candle
    if behind <= STALE_AFTER_PERIODS * period_length(resolution) + DELIVERY_GRACE:
        return CollectionState.COLLECTING
    if market_open is None:
        return CollectionState.UNKNOWN
    return CollectionState.STALLED if market_open else CollectionState.MARKET_CLOSED


async def read_status(
    conn: asyncpg.Connection,
    market_open: dict[tuple[str, Resolution], bool] | None = None,
    now: datetime | None = None,
) -> list[TrackedPairStatus]:
    """Every tracked pair with the time of its newest candle and how collection is going.

    `market_open` maps a pair to whether its instrument is currently tradeable, as the
    gateway reports it. Pairs it says nothing about come back `UNKNOWN` rather than being
    guessed at.
    """
    moment = now or datetime.now(UTC)
    lookup = market_open or {}

    statuses = []
    for row in await conn.fetch(_SELECT_STATUS):
        resolution = Resolution(row["resolution"])
        latest = row["latest_candle"]
        statuses.append(
            TrackedPairStatus(
                symbol=row["symbol"],
                resolution=resolution,
                added_at=row["added_at"],
                collect_from=row["collect_from"],
                earliest_candle=row["earliest_candle"],
                latest_candle=latest,
                collection=collection_state(
                    resolution, latest, moment, lookup.get((row["symbol"], resolution))
                ),
            )
        )
    return statuses


async def add_pair(
    conn: asyncpg.Connection,
    instruments: GatewayInstruments,
    symbol: str,
    resolution: Resolution,
    limit: int,
    collect_from: datetime | None = None,
    default_bars: int = 5000,
) -> TrackedPair:
    """Validate a pair against the gateway, then start collecting it.

    Validation first, and against the gateway rather than a list kept here: the archive
    does not own the instrument catalogue and a pair the provider cannot serve is one that
    would sit on the list forever collecting nothing.
    """
    try:
        collectable = await instruments.is_collectable(symbol, resolution)
    except GatewayRefused as err:
        raise UnknownPair(
            f"the gateway would not serve {symbol} at {resolution.value}: {err.detail}"
        ) from err
    except GatewayUnreachable:
        # Deliberately not a TrackingRefused: the pair was not rejected, it was never
        # asked about. Retrying makes sense here and does not for a refusal, so the two
        # must not reach an operator as the same thing.
        raise

    if not collectable:
        raise UnknownPair(
            f"the gateway has no candles for {symbol} at {resolution.value}, so collecting "
            "it would archive nothing"
        )

    return await track(conn, symbol, resolution, limit, collect_from, default_bars)


async def decide_late_pairs(
    instruments: GatewayInstruments,
    market_status: MarketStatus,
    statuses: list[TrackedPairStatus],
    moment: datetime,
) -> list[tuple[TrackedPairStatus, CollectionState]]:
    """Turn `UNKNOWN` into `STALLED` or `MARKET_CLOSED` where the gateway can say which.

    **Only the late ones are asked about.** A pair whose newest candle is fresh reads
    `COLLECTING` whatever the market is doing, so a request about it would spend the
    gateway's shared allowance to learn nothing that changes an answer. On a healthy
    archive that leaves nothing to ask, and this costs one round trip per late *symbol* —
    not per pair, because the same instrument at two resolutions has one market.

    A gateway that will not answer leaves the state `UNKNOWN`, which is what it already
    was. The list is the archive's own and worth returning; not knowing why one pair is
    late is not a reason to fail the whole read.
    """
    late = sorted(
        {status.symbol for status in statuses if status.collection is CollectionState.UNKNOWN}
    )
    if not late:
        return [(status, status.collection) for status in statuses]

    open_now = dict(
        await asyncio.gather(*(market_status.of(instruments, symbol) for symbol in late))
    )

    decided = []
    for status in statuses:
        collection = status.collection
        if collection is CollectionState.UNKNOWN:
            is_open = open_now.get(status.symbol)
            if is_open is not None:
                collection = collection_state(
                    status.resolution, status.latest_candle, moment, is_open
                )
        decided.append((status, collection))
    return decided
