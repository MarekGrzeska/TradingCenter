"""What the archive is collecting — asked at two resolutions, because the two questions
have very different prices.

`list_tracked_symbols` answers "what do we follow at all", one row per symbol.
`list_tracked_pairs` answers "what exactly is being collected and how healthy is it",
one row per symbol *and* resolution — which for five symbols is thirty rows, most of
them the same answer repeated seven times.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from ..client import UpstreamClient
from ._shared import READ_ONLY, raise_for_status

# Least healthy first. A symbol whose five-minute candles have stalled is a symbol to
# warn about even when its weekly ones are fine, so the summary takes the worst state
# rather than the commonest: over-warning is undone by one call to `list_tracked_pairs`,
# while a symbol reported as collecting when half of it is not is an answer nobody
# checks twice.
_COLLECTION_SEVERITY = ("stalled", "unknown", "never_collected", "market_closed", "collecting")


def _severity(state: str) -> int:
    try:
        return _COLLECTION_SEVERITY.index(state)
    except ValueError:
        # A state this module has never heard of ranks worst, not best. market-data
        # naming a new one is not a reason to call the symbol healthy on its behalf.
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


def _pair_out(row: dict) -> TrackedPairOut:
    latest = row.get("latest_candle")
    age_seconds = None
    if latest is not None:
        moment = datetime.fromisoformat(latest)
        age_seconds = (datetime.now(UTC) - moment).total_seconds()
    return TrackedPairOut(
        symbol=row["symbol"],
        resolution=row["resolution"],
        collection=row["collection"],
        candle_count=row["candle_count"],
        latest_candle_age_seconds=age_seconds,
    )


def register(mcp: FastMCP, upstream: UpstreamClient) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def list_tracked_symbols() -> list[TrackedSymbolOut]:
        """Which symbols this archive follows at all — one row each, no resolutions.

        The cheap answer to "what do we trade": the same `/pairs` reading as
        `list_tracked_pairs`, folded to one row per symbol. Reach for that one instead
        when the resolution is the point — how many candles are held, how old the newest
        one is, or which timeframe in particular has stalled.

        `collection` here is the least healthy state among that symbol's resolutions, so
        a symbol shown as collecting is collecting everywhere.
        """
        response = await upstream.get("/pairs")
        await raise_for_status(response)
        by_symbol: dict[str, list[str]] = {}
        for row in response.json():
            by_symbol.setdefault(row["symbol"], []).append(row["collection"])
        return [
            TrackedSymbolOut(symbol=symbol, collection=_worst_collection(states))
            for symbol, states in sorted(by_symbol.items())
        ]

    @mcp.tool(annotations=READ_ONLY)
    async def list_tracked_pairs() -> list[TrackedPairOut]:
        """Which pairs market-data is collecting right now, and whether collection is
        actually happening — per symbol *and* resolution, with candle counts and the age
        of the newest one. A price or an indicator for a pair nobody tracks is not "the
        market is quiet", it is a question this archive was never asked to answer.

        Use `list_tracked_symbols` when the question is only which symbols exist; this
        one answers at seven rows per symbol and is worth that when the resolution, the
        counts or the age of the data are part of what is being asked.
        """
        response = await upstream.get("/pairs")
        await raise_for_status(response)
        return [_pair_out(row) for row in response.json()]
