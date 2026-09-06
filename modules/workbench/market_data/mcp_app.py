"""What this module announces on its tool surface: its name, its instructions, and which tools go
on it. A separate process until 19 August 2026 and a written-out copy of the mounting until this
change; the shape is `tc_mcp_kit.mounted_server` now, and what it lost was never a tool or a ceiling."""

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
    "Read-only tools over this archive's candles and indicator catalogue. No tool here "
    "changes state: starting collection on a pair, or deleting one, happens in the "
    "terminal, never through this server."
)


def build_server(app) -> FastMCP:
    return _build("market-data", INSTRUCTIONS, lambda mcp: tools.register(mcp, ToolContext(app=app)))


def build_mcp_app(app) -> tuple[FastMCP, ASGIApp]:
    """The streamable-http transport and the server behind it, to be mounted under `/mcp`."""
    return _mount(build_server(app))
