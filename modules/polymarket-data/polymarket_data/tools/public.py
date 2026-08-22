"""Two ways into Polymarket's public database: by phrase, and by category.

Both read the provider live and neither writes anything. They exist as two tools rather than
one because they answer questions a model asks differently: "is there a market about X" has a
phrase in it, and "what is there about tariffs at all" does not — it has a subject, and
guessing phrases at a subject is how a model misses the market it was asked for.

Both answers are aggressively projected. A listing of a hundred events measured 10 MiB on the
provider and there is no parameter to ask for less, so the reduction is this module's job.
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from .. import store
from ..provider import ProviderError
from ._shared import PROBABILITY, READ_ONLY, ToolContext

# How many events a browse answers with at most. Twenty rows of six fields is something a
# model can actually read; the provider will happily send a hundred events of ninety fields.
MAX_RESULTS = 25


class PublicMarket(BaseModel):
    question: str
    label: str | None = Field(
        default=None, description="what this market is called inside its event"
    )
    outcomes: list[str]
    prices: list[float] = Field(description=f"one per outcome, in the same order — {PROBABILITY}")


class PublicEvent(BaseModel):
    event_id: str = Field(description="pass this to track_event to start collecting it")
    slug: str
    title: str
    url: str
    volume: float | None = Field(default=None, description="lifetime volume in USD")
    ends_at: str | None = None
    market_count: int
    tracked: bool = Field(
        description="true when this module already observes it — checked here so a model "
        "does not have to make a second call, and so 'add it' does not mean 'add it again'"
    )
    markets: list[PublicMarket] = Field(
        description="at most three, as a sample of what the event asks; the whole event "
        "comes from get_event once it is tracked"
    )


def _markets_of(payload: dict) -> list[PublicMarket]:
    out: list[PublicMarket] = []
    for raw in (payload.get("markets") or [])[:3]:
        if not isinstance(raw, dict):
            continue
        try:
            names = list(json.loads(raw.get("outcomes") or "[]"))
            prices = [float(price) for price in json.loads(raw.get("outcomePrices") or "[]")]
        except (ValueError, TypeError):
            names, prices = [], []
        out.append(
            PublicMarket(
                question=str(raw.get("question") or ""),
                label=raw.get("groupItemTitle") or None,
                outcomes=[str(name) for name in names],
                prices=prices,
            )
        )
    return out


async def _project(ctx: ToolContext, payloads: list[dict]) -> list[PublicEvent]:
    async with ctx.pool.acquire() as conn:
        tracked = {
            event.provider_event_id
            for event in await store.load_events(conn, include_ended=False)
        }
    return [
        PublicEvent(
            event_id=str(payload.get("id")),
            slug=str(payload.get("slug") or ""),
            title=str(payload.get("title") or ""),
            url=f"https://polymarket.com/event/{payload.get('slug')}",
            volume=float(payload["volume"]) if payload.get("volume") is not None else None,
            ends_at=payload.get("endDate"),
            market_count=len(payload.get("markets") or []),
            tracked=str(payload.get("id")) in tracked,
            markets=_markets_of(payload),
        )
        for payload in payloads
    ]


def register(mcp: FastMCP, ctx: ToolContext) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def search_events(query: str, limit: int = 10) -> list[PublicEvent] | dict:
        """Search Polymarket's public database by phrase. Reads the provider live and
        collects nothing — starting to collect an event is track_event, and only that.
        """
        try:
            found = await ctx.provider.search_events(query, limit=min(limit, MAX_RESULTS))
        except ProviderError as err:
            return {"refused": f"the provider could not be searched: {err}", "retryable": True}
        return await _project(ctx, found)

    @mcp.tool(annotations=READ_ONLY)
    async def browse_events(
        tag: str | None = None,
        order: str = "volume24hr",
        limit: int = 20,
        offset: int = 0,
    ) -> list[PublicEvent] | dict:
        """Browse Polymarket's public database by category rather than by phrase.

        `tag` is one of the provider's own tag ids (politics, elections and so on); leave it
        out for everything currently open. `order` is volume24hr, volume, liquidity or
        endDate. Use this when the operator asks about a subject rather than a specific
        question — guessing phrases at a subject is how the market they meant gets missed.

        Reads the provider live and collects nothing.
        """
        try:
            found = await ctx.provider.browse_events(
                tag_id=tag, order=order, limit=min(limit, MAX_RESULTS), offset=offset
            )
        except ProviderError as err:
            return {"refused": f"the provider could not be browsed: {err}", "retryable": True}
        return await _project(ctx, found)
