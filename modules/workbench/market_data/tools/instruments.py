"""Finding the symbol other tools expect."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from ..errors import GatewayError
from . import reduce
from ._shared import READ_ONLY, ToolContext
from .errors import ToolRefusal

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


def register(mcp: FastMCP, ctx: ToolContext) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def search_instruments(query: str) -> SearchInstrumentsOut:
        """Find the symbol this archive and the other tools here expect, from a name a
        person would actually type — "Nasdaq" rather than "US100". Up to 10 matches;
        further ones are counted in `omitted`, not dropped silently.
        """
        # The one tool whose answer still crosses a network: the catalogue belongs to capital-gateway
        # and this archive holds the only key. A failure there reaches the model as a refusal naming it.
        try:
            rows = await ctx.instruments.search(query)
        except GatewayError as failed:
            raise ToolRefusal(f"the instrument catalogue is unreachable: {failed}") from failed

        kept, dropped = reduce.truncate(rows, SEARCH_LIMIT)
        return SearchInstrumentsOut(
            query=query,
            results=[
                InstrumentOut(
                    symbol=row["symbol"],
                    name=row["name"],
                    asset_class=row["asset_class"],
                    tradeable=row["tradeable"],
                )
                for row in kept
            ],
            omitted=dropped,
        )
