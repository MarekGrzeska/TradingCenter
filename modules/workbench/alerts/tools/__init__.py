"""The tools this package serves at `/mcp`. Two read; one proposes a change and saves nothing. A rule decides who is told what,
and the only way one is made, changed or removed is the operator's screen — a test holds the surface to that."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import proposing, reading
from ._shared import ToolContext


def register(mcp: FastMCP, ctx: ToolContext) -> None:
    reading.register(mcp, ctx)
    proposing.register(mcp, ctx)
