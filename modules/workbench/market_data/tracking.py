"""Which pairs are collected — the operator's standing decision, and how it is going. Untracking flips
the row and keeps every candle; discarding data is explicit and separate (`deletion.py`)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from enum import Enum

import asyncpg
from pydantic import BaseModel

from .db import fetch_one
from .errors import GatewayRefused, GatewayUnreachable
from .gateway.instruments import GatewayInstruments
from .market_status import MarketStatus
from .models import Resolution, TrackedPairState
from .periods import period_length

# How far behind the newest candle may fall before collection is called stalled. Two periods rather
# than one: a candle is written once its period closes, so the newest is legitimately one period old.
STALE_AFTER_PERIODS = 2

# Plus however long the candle takes to arrive once the period closed, which does not scale with the
# resolution. Measured 2026-08-08: 52 to 169 seconds, so two periods alone flipped MINUTE pairs at random.
DELIVERY_GRACE = timedelta(minutes=3)


class TrackingRefused(Exception):
    """A pair was not taken on, and this says why. Refusals are named rather than returned as a bare
    false, because each is something an operator has to read and act on."""


class UnknownPair(TrackingRefused):
    """The gateway could not produce a candle for this symbol at this resolution."""


class LimitReached(TrackingRefused):
    """The configured ceiling on tracked pairs is full. Refusing loudly is the point: the alternative
    is accepting the pair and quietly not collecting some of them."""


class CollectionState(str, Enum):
    """Whether data is actually arriving, as far as the archive can tell. Being on the list proves
    nothing — a subscription can die without a sound."""

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
    # The oldest period collected, which is how far back the data actually reaches. `collect_from` is
    # only where it was asked to reach, and an unfinished job leaves the two far apart.
    earliest_candle: datetime | None
    latest_candle: datetime | None
    collection: CollectionState
    # How many candles are actually collected: a wide range with a thin scatter inside it looks the
    # same as one collected densely. Defaulted because a handful of call sites describe timing alone.
    candle_count: int = 0


def default_collect_from(resolution: Resolution, default_bars: int, now: datetime) -> datetime:
    """Where history starts for a pair nobody gave an explicit moment for — the same depth a single fill
    has always reached back to, so a plain `track()` behaves as it did before `collect_from` existed."""
    return now - period_length(resolution) * default_bars


# A single key rather than one per pair: the ceiling counts every tracked pair, so two additions
# racing each other have to be serialised against the same thing, not against their own rows.
_LOCK_TRACKING = "SELECT pg_advisory_xact_lock(hashtextextended('market_data.tracked_pairs', 0))"

_COUNT_TRACKED = "SELECT count(*) AS tracked FROM tracked_pairs WHERE state = 'tracked'"

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

# One query for every pair's oldest and newest candle. `count(c.period_start)`, not `count(*)`: with a
# LEFT JOIN the latter counts the joined all-NULL row, so a pair with nothing reports one candle.
_SELECT_STATUS = """
    SELECT t.symbol, t.resolution, t.added_at, t.collect_from,
           min(c.period_start) AS earliest_candle,
           max(c.period_start) AS latest_candle,
           count(c.period_start) AS candle_count
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
    """Start collecting a pair, or raise `LimitReached` saying why not. Re-tracking keeps the original
    `added_at` and can only pull `collect_from` earlier, never push it later."""
    resolved_from = collect_from or default_collect_from(
        resolution, default_bars, datetime.now(UTC)
    )

    # The count and the insert have to be one atomic thing: two additions racing each other would
    # both read `limit - 1` and both succeed, putting the archive one connection over the ceiling.
    async with conn.transaction():
        await conn.execute(_LOCK_TRACKING)

        if not await conn.fetchval(_IS_TRACKED, symbol, resolution.value):
            tracked = (await fetch_one(conn, _COUNT_TRACKED))["tracked"]
            if tracked >= limit:
                raise LimitReached(
                    f"already collecting {tracked} (symbol, resolution) pairs, which is the "
                    f"configured ceiling of {limit}. One instrument on several time frames "
                    f"is several pairs. The gateway holds one provider connection per pair "
                    f"and the provider limits how many a session may hold, so stop "
                    f"collecting a pair or raise MAX_TRACKED_PAIRS deliberately."
                )

        return _pair(await fetch_one(conn, _TRACK, symbol, resolution.value, resolved_from))


async def untrack(
    conn: asyncpg.Connection, symbol: str, resolution: Resolution
) -> TrackedPair | None:
    """Stop collecting a pair. The candles stay, and so does the row: the moment collection stopped is
    the left edge of the gap that tracking it again has to close."""
    row = await conn.fetchrow(_UNTRACK, symbol, resolution.value)
    return _pair(row) if row else None


async def read_tracked(conn: asyncpg.Connection) -> list[TrackedPair]:
    """Every pair currently being collected, oldest decision first. This is what a restart reads, and
    there is no list in a file to disagree with it."""
    return [_pair(row) for row in await conn.fetch(_SELECT_TRACKED)]


async def is_tracked(conn: asyncpg.Connection, symbol: str, resolution: Resolution) -> bool:
    return await conn.fetchval(_IS_TRACKED, symbol, resolution.value) is not None


async def read_collect_from(
    conn: asyncpg.Connection, symbol: str, resolution: Resolution
) -> datetime | None:
    """The moment this pair's history is meant to reach back to, or `None` if it is not tracked. `None`
    means there is nothing to fetch for, not "use the old default"."""
    return await conn.fetchval(_SELECT_COLLECT_FROM, symbol, resolution.value)


def collection_state(
    resolution: Resolution,
    latest_candle: datetime | None,
    now: datetime,
    market_open: bool | None = None,
) -> CollectionState:
    """How collection is going for one pair, from the age of its newest candle. `market_open` is passed
    in: this module has no session calendar, and inventing one is a confident wrong answer twice a day."""
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
    """Every tracked pair with the time of its newest candle and how collection is going. Pairs the
    gateway says nothing about come back `UNKNOWN` rather than being guessed at."""
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
                candle_count=row["candle_count"],
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
    """Validate a pair against the gateway, then start collecting it. Against the gateway rather than a
    list kept here: a pair the provider cannot serve would sit on the list forever collecting nothing."""
    try:
        collectable = await instruments.is_collectable(symbol, resolution)
    except GatewayRefused as err:
        raise UnknownPair(
            f"the gateway would not serve {symbol} at {resolution.value}: {err.detail}"
        ) from err
    except GatewayUnreachable:
        # Deliberately not a TrackingRefused: the pair was not rejected, it was never asked about.
        # Retrying makes sense here and does not for a refusal.
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
    """Turn `UNKNOWN` into `STALLED` or `MARKET_CLOSED` where the gateway can say which. Only the late
    ones are asked about, one round trip per late *symbol*; a gateway that will not answer leaves it."""
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
