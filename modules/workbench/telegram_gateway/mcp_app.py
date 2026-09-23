"""What this module announces on its tool surface: its name, its instructions, and which tools go on
it. Two, and one of them leaves the system — creating a bot and binding a destination stay REST-only,
out of any conversation's reach. The mounting is `tc_mcp_kit.mounted_server`."""

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
    "The one door to Telegram: send a notification to somebody the operator has already bound. "
    "This is the only surface here that does something visible outside this system, so a message "
    "sent is sent — there is no queue, no retry and no history to read back. A message is "
    "addressed by destination name, never by chat id; call telegram_destinations first, because "
    "the names are the operator's and cannot be guessed. Creating a bot, deleting one and binding "
    "a destination are deliberately absent: they outlive the conversation and belong to the "
    "operator, who does them through this module's REST contract."
)


def build_server(app) -> FastMCP:
    return _build("telegram-gateway", INSTRUCTIONS, lambda mcp: tools.register(mcp, ToolContext(app=app)))


def build_mcp_app(app) -> tuple[FastMCP, ASGIApp]:
    """The streamable-http transport and the server behind it, to be mounted under `/mcp`."""
    return _mount(build_server(app))
