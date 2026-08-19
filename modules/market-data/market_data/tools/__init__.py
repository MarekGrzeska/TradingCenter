"""The tool surface this module serves at `/mcp`.

The reduction, the ceilings and the sentences about uncertainty — everything a model
needs that a chart does not. A chart wants every candle; a model wants a summary, so the
same archive read comes out reduced rather than whole.

Registration order is the order a client sees the tools in, and it is the order a question
travels: which pairs exist, then their candles, then the instrument behind a symbol, then
what can be computed on top.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import candles, indicators, instruments, pairs, resources
from ._shared import ToolContext


def register(mcp: FastMCP, ctx: ToolContext) -> None:
    pairs.register(mcp, ctx)
    candles.register(mcp, ctx)
    instruments.register(mcp, ctx)
    indicators.register(mcp, ctx)
    resources.register(mcp, ctx)
