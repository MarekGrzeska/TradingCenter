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


def build_server(app) -> FastMCP:
    return _build("strategies", INSTRUCTIONS, lambda mcp: tools.register(mcp, ToolContext(app=app)))
