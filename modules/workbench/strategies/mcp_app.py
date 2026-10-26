"""What this package announces as tools: its name, its instructions and which tools go on it. Built, never mounted: the
conversation calls it as a function in this process, and no caller over a network would use a door to writing tools
(design D7)."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from tc_mcp_kit.mounted_server import build_server as _build

from . import tools
from .tools import ToolContext

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


def build_team_server(app) -> FastMCP:
    def register(mcp: FastMCP) -> None:
        tools.register(mcp, ToolContext(app=app))
        # Private, as in `tc_mcp_kit.tool_schemas`: FastMCP has no public list of what is registered before serving.
        for name in [tool.name for tool in mcp._tool_manager.list_tools() if tool.name not in TEAM_TOOLS]:
            mcp.remove_tool(name)

    return _build("strategies", TEAM_INSTRUCTIONS, register)
