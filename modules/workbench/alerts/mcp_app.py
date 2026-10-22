"""What this package announces on its tool surface: its name, its instructions, and which tools go on it. The mounting is
`tc_mcp_kit.mounted_server`."""

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
    "The notification rules the operator has set — what is watched, who is told, and what became of each time a rule went "
    "off. A rule is made, changed and removed on the operator's screen; propose_alert_change shows what a described change "
    "would make of a rule and saves nothing. When the operator asks why an alert did "
    "not come, call alert_fires for that rule: a rule that is quiet because nothing happened and one that is quiet because "
    "the tool it reads was down, or because it was inside its cool-down, look the same until the history is read."
)


def build_server(app) -> FastMCP:
    return _build("alerts", INSTRUCTIONS, lambda mcp: tools.register(mcp, ToolContext(app=app)))


def build_mcp_app(app) -> tuple[FastMCP, ASGIApp]:
    """The streamable-http transport and the server behind it, to be mounted under `/mcp`."""
    return _mount(build_server(app))
