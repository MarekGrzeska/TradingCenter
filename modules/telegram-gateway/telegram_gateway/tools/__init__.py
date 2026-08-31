"""The two tools this module serves at `/mcp`. One of them writes, and it is the only tool in this
system whose effect is visible outside it — which is why there are two rather than the seven the REST
contract has: creating a bot and binding a destination are the operator's, not the conversation's."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import messages
from ._shared import ToolContext


def register(mcp: FastMCP, ctx: ToolContext) -> None:
    messages.register(mcp, ctx)
