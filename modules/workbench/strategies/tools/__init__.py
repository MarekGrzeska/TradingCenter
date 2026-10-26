"""The tools the conversation reaches as functions (`strategies-tools`), and the three of them a team reaches too. They
write strategy revisions and queue runs, and nothing else: the costs a run is made with are the operator's, set on the
screen, and no tool reaches them."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import authoring, running, signal
from ._shared import ToolContext


def register(mcp: FastMCP, ctx: ToolContext) -> None:
    authoring.register(mcp, ctx)
    running.register(mcp, ctx)
    signal.register(mcp, ctx)
