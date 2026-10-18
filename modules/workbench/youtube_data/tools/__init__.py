"""The nine tools this package serves at `/mcp`. Five read the archive, one looks around at the source's expense, and three add
to what is followed or queued. None removes anything and none deletes a film or a reading — the operator's screen is the
only way something leaves the list, and a test holds the surface to that."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import films, watch
from ._shared import ToolContext


def register(mcp: FastMCP, ctx: ToolContext) -> None:
    films.register(mcp, ctx)
    watch.register(mcp, ctx)
