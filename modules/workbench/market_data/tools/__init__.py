"""The tool surface this module serves at `/mcp`. A chart wants every candle and a model wants a
summary, so the same archive read comes out reduced; registration order is the order a question travels."""

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
