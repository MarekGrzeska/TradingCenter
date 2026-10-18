"""The two tools this package serves at `/mcp`. Both read. A rule decides who is told what, and the only way one is made,
changed or removed is the operator's screen — a test holds the surface to that."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import reading
from ._shared import ToolContext


def register(mcp: FastMCP, ctx: ToolContext) -> None:
    reading.register(mcp, ctx)
