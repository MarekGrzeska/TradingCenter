"""The reads that have two consumers: the REST routers and the tool surface at `/mcp`.

Everything here used to live in a router body, which was fine while a router was the only
way in. It stopped being fine when the tools moved into this process: a tool re-deriving
"collected beats computed" or the three states of a forming candle would be a second copy
of a decision that has been wrong twice already, and it would drift the way
`agent`/`teams`'s `tools/client.py` pair drifts — the disease this change exists to stop
rather than relocate.

Nothing here builds a wire model. Routers turn these into `contract.py` shapes and tools
turn them into their own; both read the same answer.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum

import asyncpg

from .coverage import earliest_reachable, read_coverage, uncovered_within
from .gateway import GatewayInstruments
from .hub import Hub
from .market_status import MarketStatus
from .models import Candle, CoverageRange, Resolution
from .rollups import DERIVABLE, DerivedCandle, read_derived
from .store import read_candles
from .tracking import (
    CollectionState,
    TrackedPairStatus,
    decide_late_pairs,
    read_status,
    read_tracked,
)

DEFAULT_WINDOW = timedelta(days=1)


class WindowRejected(ValueError):
    """The requested range is the thing that is wrong, not the archive."""


class FormingState(str, Enum):
    """Why an answer about the period being built carries no candle — or that it does.

    Mirrors `contract.FormingState`; kept apart because that one is the wire and this one
    is the decision. The three no-candle cases lead an operator to three different places,
    which is why this is not a nullable candle.
    """

    FORMING = "forming"
    NOT_TRACKED = "not_tracked"
    MARKET_CLOSED = "market_closed"
    NO_QUOTES = "no_quotes"


@dataclass(frozen=True)
class Series:
    candles: Sequence[Candle | DerivedCandle]
    derived: bool
    uncovered: Sequence[tuple[datetime, datetime]]


@dataclass(frozen=True)
class Forming:
    state: FormingState
    resolution: Resolution | None
    candle: Candle | None
    market_open: bool | None


@dataclass(frozen=True)
class Coverage:
    ranges: Sequence[CoverageRange]
    earliest_reachable: datetime | None


def window(
    from_: datetime | None, to: datetime | None, default: timedelta = DEFAULT_WINDOW
) -> tuple[datetime, datetime]:
    """The requested range, with defaults and both ends carrying a zone.

    A naive bound is read as UTC rather than refused: it is the commonest way to write one
    by hand, and the archive stores instants, so the alternative is a refusal for something
    that has exactly one sensible reading.
    """
    end = to or datetime.now(UTC)
    start = from_ or end - default
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    if end < start:
        raise WindowRejected(f"`to` is before `from`: {start.isoformat()} to {end.isoformat()}")
    return start, end


async def read_series(
    conn: asyncpg.Connection,
    symbol: str,
    resolution: Resolution,
    start: datetime,
    end: datetime,
) -> Series:
    """Collected beats computed, and the order matters more than it looks.

    A resolution being *derivable* does not mean this pair was derived: an operator may
    track a pair at HOUR, in which case ingest fetches and stores the provider's own hourly
    candles and nothing ever builds a rollup for it, because rollups are refreshed off the
    minute series that pair does not have. Reading the rollup table unconditionally answered
    such a pair with an empty series while coverage said the range was verified — which
    reads as "the market was shut all day", the one confident wrong answer this module
    exists to prevent.
    """
    series: Sequence[Candle | DerivedCandle] = await read_candles(
        conn, symbol, resolution, start, end
    )
    derived = False
    if not series and resolution in DERIVABLE:
        series = await read_derived(conn, symbol, resolution, start, end)
        derived = True
    gaps = await uncovered_within(conn, symbol, resolution, start, end)
    return Series(candles=series, derived=derived, uncovered=gaps)


async def read_forming(
    conn: asyncpg.Connection,
    hub: Hub,
    instruments: GatewayInstruments,
    market_status: MarketStatus,
    symbol: str,
    resolution: Resolution | None,
) -> Forming:
    """The period being built right now, and — when there is none — which of three reasons.

    The market is asked about even when a candle is found: a price with no session behind
    it cannot be told from a price that stopped moving an hour ago, and that answer is
    cached per symbol either way.
    """
    tracked = [pair for pair in await read_tracked(conn) if pair.symbol == symbol]
    if not tracked:
        return Forming(
            state=FormingState.NOT_TRACKED,
            resolution=resolution,
            candle=None,
            market_open=None,
        )

    _, market_open = await market_status.of(instruments, symbol)

    if resolution is not None:
        candle = hub.forming(symbol, resolution)
        answered_with = resolution
    else:
        answered_with = next(iter(hub.forming_resolutions(symbol)), None)
        candle = hub.forming(symbol, answered_with) if answered_with else None

    if candle is None:
        return Forming(
            # `market_open is None` — the gateway would not say — falls to `no_quotes`
            # rather than to `market_closed`: claiming a closed market on the strength of
            # an unanswered question is the one wrong answer here that reads as certain.
            state=(FormingState.MARKET_CLOSED if market_open is False else FormingState.NO_QUOTES),
            resolution=resolution,
            candle=None,
            market_open=market_open,
        )

    return Forming(
        state=FormingState.FORMING,
        resolution=answered_with,
        candle=candle,
        market_open=market_open,
    )


async def read_pair_coverage(
    conn: asyncpg.Connection, symbol: str, resolution: Resolution
) -> Coverage:
    return Coverage(
        ranges=await read_coverage(conn, symbol, resolution),
        earliest_reachable=await earliest_reachable(conn, symbol, resolution),
    )


async def read_pairs(
    conn: asyncpg.Connection,
    instruments: GatewayInstruments,
    market_status: MarketStatus,
    now: datetime,
) -> list[tuple[TrackedPairStatus, CollectionState]]:
    """Every tracked pair with what its collection is actually doing."""
    statuses = await read_status(conn, now=now)
    return await decide_late_pairs(instruments, market_status, statuses, now)
