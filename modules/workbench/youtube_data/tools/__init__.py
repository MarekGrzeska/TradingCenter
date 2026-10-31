"""The eight tools this package's models call. Four read the archive, one looks around at the source's expense, and three add
to what is followed or queued. None removes anything and none deletes a film or a reading — the operator's screen is the
only way something leaves the list, and a test holds the surface to that. `/mcp` serves two more, the prompts' words, to
the operator's own client alone (`prompts`)."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import films, prompts, watch
from ._shared import ToolContext


def register(mcp: FastMCP, ctx: ToolContext) -> None:
    films.register(mcp, ctx)
    watch.register(mcp, ctx)


def register_for_the_operator(mcp: FastMCP, ctx: ToolContext) -> None:
    register(mcp, ctx)
    prompts.register(mcp, ctx)
