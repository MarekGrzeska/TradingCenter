"""The tools this package serves at `/mcp`. Registered by module as they arrive; a surface with none is still mounted,
so the session manager and the caller record are exercised from the first commit."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ._shared import ToolContext


def register(mcp: FastMCP, ctx: ToolContext) -> None:
    del mcp, ctx
