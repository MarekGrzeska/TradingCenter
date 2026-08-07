"""Which pairs are collected — the operator's standing decision, and how it is going.

Nothing is archived because somebody looked at a chart. Collecting a pair means holding a
provider connection open around the clock, and the provider limits how many a session may
hold, so spending one is a decision rather than a side effect of browsing. That is the
whole reason this module exists instead of a list in a configuration file: a file needs
access to the machine and a restart, and neither belongs in the loop of "archive this
too".

Untracking stops collection and keeps every candle. An archive that discards data when
its configuration changes is not an archive, so the row is flipped rather than deleted —
which also leaves the record of when collection stopped, and that is the gap a later
re-add has to close.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

import asyncpg
from pydantic import BaseModel

from .errors import GatewayRefused, GatewayUnreachable
from .gateway.instruments import GatewayInstruments
from .models import Resolution, TrackedPairState
from .periods import period_length

# How far behind the newest candle may fall before collection is called stalled. Two
# periods rather than one: a candle is only written once its period closes, so at any
# moment the newest one is legitimately up to one period old, and a threshold of one
# would call every healthy pair broken every period.
STALE_AFTER_PERIODS = 2


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


class TrackedPairStatus(BaseModel):
    """A tracked pair and how its collection is going."""

    symbol: str
    resolution: Resolution
    added_at: datetime
    latest_candle: datetime | None
    collection: CollectionState


# A single key rather than one per pair: the ceiling counts every tracked pair, so two
# additions racing each other have to be serialised against the same thing, not against
# their own rows. `hashtextextended` gives the bigint the advisory lock functions take.
_LOCK_TRACKING = "SELECT pg_advisory_xact_lock(hashtextextended('market_data.tracked_pairs', 0))"

_COUNT_TRACKED = "SELECT count(*) FROM tracked_pairs WHERE state = 'tracked'"

_TRACK = """
    INSERT INTO tracked_pairs (symbol, resolution, state, added_at, untracked_at)
    VALUES ($1, $2, 'tracked', now(), NULL)
    ON CONFLICT (symbol, resolution) DO UPDATE SET
        state = 'tracked',
        untracked_at = NULL
    RETURNING symbol, resolution, state, added_at, untracked_at
"""

_UNTRACK = """
    UPDATE tracked_pairs
       SET state = 'untracked', untracked_at = now()
     WHERE symbol = $1 AND resolution = $2 AND state = 'tracked'
    RETURNING symbol, resolution, state, added_at, untracked_at
"""

_SELECT_TRACKED = """
    SELECT symbol, resolution, state, added_at, untracked_at
      FROM tracked_pairs
     WHERE state = 'tracked'
     ORDER BY added_at, symbol, resolution
"""

_SELECT_ALL = """
    SELECT symbol, resolution, state, added_at, untracked_at
      FROM tracked_pairs
     ORDER BY added_at, symbol, resolution
"""

_IS_TRACKED = """
    SELECT 1 FROM tracked_pairs
     WHERE symbol = $1 AND resolution = $2 AND state = 'tracked'
     LIMIT 1
"""

# One query for every tracked pair's newest candle rather than one query per pair. The
# left join keeps a pair that has never collected anything, which is a state an operator
# needs to see rather than a row that quietly goes missing.
_SELECT_STATUS = """
    SELECT t.symbol, t.resolution, t.added_at, max(c.period_start) AS latest_candle
      FROM tracked_pairs t
      LEFT JOIN candles c
        ON c.symbol = t.symbol AND c.resolution = t.resolution
     WHERE t.state = 'tracked'
     GROUP BY t.symbol, t.resolution, t.added_at
     ORDER BY t.added_at, t.symbol, t.resolution
"""


def _pair(row: asyncpg.Record) -> TrackedPair:
    return TrackedPair(
        symbol=row["symbol"],
        resolution=Resolution(row["resolution"]),
        state=TrackedPairState(row["state"]),
        added_at=row["added_at"],
        untracked_at=row["untracked_at"],
    )


async def track(
    conn: asyncpg.Connection, symbol: str, resolution: Resolution, limit: int
) -> TrackedPair:
    """Start collecting a pair, or raise `LimitReached` saying why not.

    Re-tracking a pair that was untracked flips it back and keeps its original `added_at`,
    because it is the same standing decision resumed rather than a new one. Its candles
    were never touched, so what it needs on resumption is the gap closed, not a fresh
    start — which is what the preserved `untracked_at` was for.
    """
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

        return _pair(await conn.fetchrow(_TRACK, symbol, resolution.value))


async def untrack(
    conn: asyncpg.Connection, symbol: str, resolution: Resolution
) -> TrackedPair | None:
    """Stop collecting a pair. Returns `None` if it was not being collected.

    The candles stay, and so does the row: the moment collection stopped is the left edge
    of the gap that tracking it again will have to close.
    """
    row = await conn.fetchrow(_UNTRACK, symbol, resolution.value)
    return _pair(row) if row else None


async def read_tracked(conn: asyncpg.Connection) -> list[TrackedPair]:
    """Every pair currently being collected, oldest decision first.

    This is what a restart reads. There is no list in a file to disagree with it.
    """
    return [_pair(row) for row in await conn.fetch(_SELECT_TRACKED)]


async def read_all(conn: asyncpg.Connection) -> list[TrackedPair]:
    """Every pair ever tracked, including the ones that were stopped."""
    return [_pair(row) for row in await conn.fetch(_SELECT_ALL)]


async def is_tracked(conn: asyncpg.Connection, symbol: str, resolution: Resolution) -> bool:
    return await conn.fetchval(_IS_TRACKED, symbol, resolution.value) is not None


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
    """
    if latest_candle is None:
        return CollectionState.NEVER_COLLECTED

    behind = now - latest_candle
    if behind <= STALE_AFTER_PERIODS * period_length(resolution):
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

    return await track(conn, symbol, resolution, limit)
