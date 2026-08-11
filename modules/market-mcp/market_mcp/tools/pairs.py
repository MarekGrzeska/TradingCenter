"""What the archive is collecting."""

from __future__ import annotations

from datetime import UTC, datetime

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from ..client import UpstreamClient
from ._shared import READ_ONLY, raise_for_status


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
    async def list_tracked_pairs() -> list[TrackedPairOut]:
        """Which pairs market-data is collecting right now, and whether collection is
        actually happening — the first thing to check before asking about a symbol,
        since a price or an indicator for a pair nobody tracks is not "the market is
        quiet", it is a question this archive was never asked to answer.
        """
        response = await upstream.get("/pairs")
        await raise_for_status(response)
        return [_pair_out(row) for row in response.json()]
