"""What the archive is collecting, asked at two resolutions because the two questions have very
different prices: one row per symbol, or one row per symbol *and* resolution."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from ..tracking import TrackedPairStatus
from ._shared import READ_ONLY, ToolContext, tracked_pairs

# Least healthy first: a symbol whose five-minute candles have stalled is worth warning about even
# when its weekly ones are fine. Over-warning is undone by one call; the opposite is not checked twice.
_COLLECTION_SEVERITY = ("stalled", "unknown", "never_collected", "market_closed", "collecting")


def _severity(state: str) -> int:
    try:
        return _COLLECTION_SEVERITY.index(state)
    except ValueError:
        # A state this list has never heard of ranks worst, not best: a new `CollectionState` is not
        # a reason to call the symbol healthy on its behalf.
        return -1


def _worst_collection(states: Iterable[str]) -> str:
    return min(states, key=_severity)


class TrackedSymbolOut(BaseModel):
    symbol: str
    collection: str = Field(
        description=(
            "the least healthy state across every resolution of this symbol: "
            "collecting, market_closed, never_collected, unknown or stalled. "
            "list_tracked_pairs is where that breaks down per resolution"
        )
    )


class TrackedPairOut(BaseModel):
    symbol: str
    resolution: str
    collection: str = Field(
        description="collecting, stalled, market_closed, unknown, or never_collected"
    )
    candle_count: int = Field(description="how many candles the archive holds for this pair")
    latest_candle_age_seconds: float | None = Field(
        default=None,
        description="seconds since the newest candle; null when the archive has none yet",
    )


def _pair_out(pair: TrackedPairStatus) -> TrackedPairOut:
    age_seconds = None
    if pair.latest_candle is not None:
        age_seconds = (datetime.now(UTC) - pair.latest_candle).total_seconds()
    return TrackedPairOut(
        symbol=pair.symbol,
        resolution=pair.resolution.value,
        collection=pair.collection.value,
        candle_count=pair.candle_count,
        latest_candle_age_seconds=age_seconds,
    )


def register(mcp: FastMCP, ctx: ToolContext) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def list_tracked_symbols() -> list[TrackedSymbolOut]:
        """Which symbols this archive follows at all — one row each, no resolutions.

        The cheap answer to "what do we trade". Reach for `list_tracked_pairs` when the
        resolution is the point: how many candles are held, how old the newest one is, or
        which timeframe in particular has stalled. `collection` here is the least healthy
        state among that symbol's resolutions, so a symbol shown as collecting is
        collecting everywhere.
        """
        by_symbol: dict[str, list[str]] = {}
        for pair in await tracked_pairs(ctx):
            by_symbol.setdefault(pair.symbol, []).append(pair.collection.value)
        return [
            TrackedSymbolOut(symbol=symbol, collection=_worst_collection(states))
            for symbol, states in sorted(by_symbol.items())
        ]

    @mcp.tool(annotations=READ_ONLY)
    async def list_tracked_pairs() -> list[TrackedPairOut]:
        """Which pairs this archive is collecting right now, and whether collection is
        actually happening — per symbol *and* resolution, with candle counts and the age
        of the newest one. A price or an indicator for a pair nobody tracks is not "the
        market is quiet", it is a question this archive was never asked to answer.

        Seven rows per symbol; `list_tracked_symbols` is the one-row-per-symbol answer
        when only the list of symbols is the point.
        """
        return [_pair_out(pair) for pair in await tracked_pairs(ctx)]
