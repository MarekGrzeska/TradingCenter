"""Finding the symbol other tools expect."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from .. import reduce
from ..client import UpstreamClient
from ..upstream import UpstreamInstrument
from ._shared import READ_ONLY, raise_for_status

SEARCH_LIMIT = 10


class InstrumentOut(BaseModel):
    symbol: str
    name: str
    asset_class: str
    tradeable: bool


class SearchInstrumentsOut(BaseModel):
    query: str
    results: list[InstrumentOut]
    omitted: int = Field(default=0, description="matches beyond the results shown")


def register(mcp: FastMCP, upstream: UpstreamClient) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def search_instruments(query: str) -> SearchInstrumentsOut:
        """Find the symbol market-data and the other tools here expect, from a name a
        person would actually type — "Nasdaq" rather than "US100". Up to 10 matches;
        further ones are counted in `omitted`, not dropped silently.
        """
        response = await upstream.get("/instruments/search", params={"q": query})
        await raise_for_status(response)
        rows = response.json()
        kept, dropped = reduce.truncate(rows, SEARCH_LIMIT)
        hits = [UpstreamInstrument.model_validate(row) for row in kept]
        return SearchInstrumentsOut(
            query=query,
            results=[
                InstrumentOut(
                    symbol=h.symbol, name=h.name, asset_class=h.asset_class, tradeable=h.tradeable
                )
                for h in hits
            ],
            omitted=dropped,
        )
