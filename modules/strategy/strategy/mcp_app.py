"""What this module announces on its tool surface: its name, its instructions, and which tools go on
it. Nothing here reaches an account — the tools report what was decided, and deciding is the loop's.
The mounting is `tc_mcp_kit.mounted_server`, with the three production notes that shaped it."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from starlette.types import ASGIApp
from tc_mcp_kit.mounted_server import (
    MOUNT_PATH,
    ToolSurfaceAddress,
    tool_surface_session,
)
from tc_mcp_kit.mounted_server import (
    build_mcp_app as _mount,
)
from tc_mcp_kit.mounted_server import (
    build_server as _build,
)

from . import tools
from .tools import ToolContext

__all__ = [
    "INSTRUCTIONS",
    "MOUNT_PATH",
    "ToolSurfaceAddress",
    "build_mcp_app",
    "build_server",
    "tool_surface_session",
]

INSTRUCTIONS = (
    "Read-only tools over the strategy platform: which strategies are watching what, and "
    "what they decided. No tool here changes anything — activating a strategy, writing a "
    "parameter set or running a backtest happens over this module's REST contract, never "
    "through this server. This module never touches an account: a setup here is a "
    "reading, not an order."
)


def build_server(app) -> FastMCP:
    return _build("strategy", INSTRUCTIONS, lambda mcp: tools.register(mcp, ToolContext(app=app)))


def build_mcp_app(app) -> tuple[FastMCP, ASGIApp]:
    """The streamable-http transport and the server behind it, to be mounted under `/mcp`."""
    return _mount(build_server(app))
