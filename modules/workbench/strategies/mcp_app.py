"""What this package announces as tools: its name, its instructions and which tools go on it. The conversation calls it
as a function in this process; the operator's own MCP client reaches the same server under `/mcp`
(`operator-mcp-access`, which reverses design D7 of `a-strategy-from-a-description`: its one reason was that no such
client existed)."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from starlette.types import ASGIApp
from tc_mcp_kit.mounted_server import MOUNT_PATH, ToolSurfaceAddress, tool_surface_session
from tc_mcp_kit.mounted_server import build_mcp_app as _mount
from tc_mcp_kit.mounted_server import build_server as _build

from . import tools
from .tools import ToolContext

__all__ = [
    "MOUNT_PATH",
    "TEAM_TOOLS",
    "ToolSurfaceAddress",
    "build_mcp_app",
    "build_server",
    "build_team_server",
    "tool_surface_session",
]

INSTRUCTIONS = (
    "The operator's trading strategies as documents, and backtests of them — research only, never an order. Read the "
    "language before writing a document, save revisions as you change one, and run a backtest when the operator asks."
)


# What a team may call (design D5): reading, and the engine's decision. Nothing that saves, drafts, queues or deletes —
# a schedule would spend the queue and the trial count on runs nobody asked for.
TEAM_TOOLS = frozenset({"list_strategies", "read_strategy", "strategy_signal"})

TEAM_INSTRUCTIONS = (
    "The operator's trading strategies, read-only, and what the backtest engine would do now for a revision — so a "
    "team trades the decision the backtest made, not its own reading of the rules."
)


def build_server(app) -> FastMCP:
    return _build("strategies", INSTRUCTIONS, lambda mcp: tools.register(mcp, ToolContext(app=app)))


def build_mcp_app(app) -> tuple[FastMCP, ASGIApp]:
    """The streamable-http transport and the server behind it, to be mounted under `/mcp`."""
    return _mount(build_server(app))


def build_team_server(app) -> FastMCP:
    def register(mcp: FastMCP) -> None:
        tools.register(mcp, ToolContext(app=app))
        # Private, as in `tc_mcp_kit.tool_schemas`: FastMCP has no public list of what is registered before serving.
        for name in [tool.name for tool in mcp._tool_manager.list_tools() if tool.name not in TEAM_TOOLS]:
            mcp.remove_tool(name)

    return _build("strategies", TEAM_INSTRUCTIONS, register)
