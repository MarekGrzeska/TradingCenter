"""The nine tools this module serves at `/mcp`.

Registration order is the order a client sees them in, and it is the order a question
travels: find something in the public database, then start collecting it, then read what has
been collected. A model handed the reads first would have to guess that anything can be
added at all.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import archive, observations, public
from ._shared import ToolContext


def register(mcp: FastMCP, ctx: ToolContext) -> None:
    public.register(mcp, ctx)
    observations.register(mcp, ctx)
    archive.register(mcp, ctx)
