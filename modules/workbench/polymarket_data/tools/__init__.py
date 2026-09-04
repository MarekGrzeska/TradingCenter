"""The nine tools this module serves at `/mcp`. Registration order is the order a question travels:
find something, start collecting it, then read what has been collected."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import archive, observations, public
from ._shared import ToolContext


def register(mcp: FastMCP, ctx: ToolContext) -> None:
    public.register(mcp, ctx)
    observations.register(mcp, ctx)
    archive.register(mcp, ctx)
