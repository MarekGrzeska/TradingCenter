"""The reads with two consumers: the REST routers and the tool surface at `/mcp`. A tool re-deriving
"collected beats computed" would be a second copy of a decision that has been wrong twice already."""

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
    """Why an answer about the period being built carries no candle — or that it does. Mirrors
    `contract.FormingState`: that one is the wire, this one the decision, and three cases are not a null."""

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
    """The requested range, with defaults and both ends carrying a zone. A naive bound is read as UTC
    rather than refused: it is the commonest way to write one, and it has exactly one sensible reading."""
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
    """Collected beats computed, and the order matters: a pair tracked at HOUR stores the provider's own
    candles and never builds a rollup, so reading the rollup table answered it with an empty series."""
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
    """The period being built right now, and — when there is none — which of three reasons. The market
    is asked about even when a candle is found: a price with no session behind it looks like a stopped one."""
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
            # `market_open is None` — the gateway would not say — falls to `no_quotes` rather than
            # `market_closed`: claiming a closed market on an unanswered question reads as certain.
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
