"""Tools this server publishes. One module, growing one function per tool: a tool is
a function of (request in, response out) with no state between calls, so a class here
would hold nothing a plain function does not already hold in its closure over
`upstream`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from .client import UpstreamClient


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


def register(mcp: FastMCP, upstream: UpstreamClient) -> None:
    @mcp.tool()
    async def list_tracked_pairs() -> list[TrackedPairOut]:
        """Which pairs market-data is collecting right now, and whether collection is
        actually happening — the first thing to check before asking about a symbol,
        since a price or an indicator for a pair nobody tracks is not "the market is
        quiet", it is a question this archive was never asked to answer.
        """
        response = await upstream.get("/pairs")
        response.raise_for_status()
        return [_pair_out(row) for row in response.json()]


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
