"""The four tools this module serves at `/mcp`. All of them read: there is no list here for a model
to add to, so a writing tool would have nothing to write that the collection loop is not writing."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import posts
from ._shared import ToolContext


def register(mcp: FastMCP, ctx: ToolContext) -> None:
    posts.register(mcp, ctx)
