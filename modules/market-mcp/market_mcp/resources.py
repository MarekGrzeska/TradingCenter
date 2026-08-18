"""MCP resources and the one prompt this module publishes.

A resource is read by URI, not called with arguments — cheaper for a client that
wants to look something up once and hold onto it, rather than pay a tool-call round
trip for the same catalogue on every turn.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .client import UpstreamClient
from .tools._shared import raise_for_status

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


def register(mcp: FastMCP, upstream: UpstreamClient) -> None:
    @mcp.resource("market://indicators/catalogue", mime_type="application/json")
    async def indicators_catalogue() -> dict:
        """The full indicator catalogue, exactly as market-data publishes it."""
        response = await upstream.get("/indicators")
        await raise_for_status(response)
        return response.json()

    @mcp.resource("market://pairs", mime_type="application/json")
    async def tracked_pairs() -> list:
        """Which pairs the archive is collecting right now."""
        response = await upstream.pairs()
        await raise_for_status(response)
        return response.json()

    @mcp.resource("market://coverage/{symbol}/{resolution}", mime_type="application/json")
    async def coverage(symbol: str, resolution: str) -> dict:
        """What the archive has verified for one pair at one resolution."""
        response = await upstream.get(f"/coverage/{symbol}", params={"resolution": resolution})
        await raise_for_status(response)
        return response.json()

    @mcp.prompt(name="analyze-symbol")
    def analyze_symbol(symbol: str, resolution: str = "MINUTE") -> str:
        """A fixed order that works: coverage, then a window summary, then
        indicators, then naming what is still not known."""
        return ANALYZE_SYMBOL_PROMPT.format(symbol=symbol, resolution=resolution)
