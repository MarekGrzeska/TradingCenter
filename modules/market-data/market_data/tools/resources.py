"""MCP resources and the one prompt the tool surface publishes. A resource is read by URI, which is
cheaper for a client that wants to look something up once than a tool call every turn."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..indicators import service
from ..reads import read_pair_coverage
from ._shared import ToolContext, resolution_of
from ._shared import tracked_pairs as read_tracked_pairs
from .candles import COVERAGE_RANGE_LIMIT, CoverageRangeOut, DescribeCoverageOut

ANALYZE_SYMBOL_PROMPT = (
    "Analyze {symbol} at {resolution} resolution. Follow this order — it is the one "
    "that avoids a confident wrong answer:\n"
    "1. Call describe_coverage for {symbol!r} first. Know what the archive has "
    "actually verified before trusting anything else it says about this symbol.\n"
    "2. Call summarize_range for {symbol!r} to see the recent window's shape — "
    "change, choppiness, its biggest move.\n"
    "3. Call compute_indicators and/or levels_near_price for {symbol!r} for the "
    "momentum and structure context the question needs.\n"
    "4. Before answering, name explicitly what is not known: any unverified range "
    "from step 1, any unsettled indicator value from step 3, or a pair "
    "list_tracked_pairs shows as not currently collecting. A margin of uncertainty "
    "stated is worth more than a number stated with false confidence."
)


def register(mcp: FastMCP, ctx: ToolContext) -> None:
    @mcp.resource("market://indicators/catalogue", mime_type="application/json")
    async def indicators_catalogue() -> dict:
        """The full indicator catalogue, exactly as this archive publishes it."""
        return service.catalogue().model_dump(mode="json", by_alias=True)

    @mcp.resource("market://pairs", mime_type="application/json")
    async def tracked_pairs() -> list:
        """Which pairs the archive is collecting right now."""
        return [pair.model_dump(mode="json") for pair in await read_tracked_pairs(ctx)]

    @mcp.resource("market://coverage/{symbol}/{resolution}", mime_type="application/json")
    async def coverage(symbol: str, resolution: str) -> dict:
        """What the archive has verified for one pair at one resolution."""
        async with ctx.pool.acquire() as conn:
            found = await read_pair_coverage(conn, symbol, resolution_of(resolution))
        ordered = sorted(found.ranges, key=lambda r: r.range_end, reverse=True)
        return DescribeCoverageOut(
            symbol=symbol,
            resolution=resolution,
            ranges=[
                CoverageRangeOut(from_=r.range_start, to=r.range_end, history_ended=r.history_ended)
                for r in ordered[:COVERAGE_RANGE_LIMIT]
            ],
            earliest_reachable=found.earliest_reachable,
            omitted_ranges=max(0, len(ordered) - COVERAGE_RANGE_LIMIT),
        ).model_dump(mode="json", by_alias=True)

    @mcp.prompt(name="analyze-symbol")
    def analyze_symbol(symbol: str, resolution: str = "MINUTE") -> str:
        """A fixed order that works: coverage, then a window summary, then
        indicators, then naming what is still not known."""
        return ANALYZE_SYMBOL_PROMPT.format(symbol=symbol, resolution=resolution)
