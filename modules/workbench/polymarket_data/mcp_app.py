"""What this module announces on its tool surface: its name, its instructions, and which tools go on
it. Three of them write, which is why the instructions say so — the mounting itself is
`tc_mcp_kit.mounted_server`, identical here to four other modules' and no longer written out."""

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
    "Prediction-market data from Polymarket: search its public database, choose what to "
    "collect, and read what has been collected. Prices are probabilities on 0..1, never "
    "percentages. Two tools change the list of what is collected — track_event and "
    "create_group — and both of them only add to it: nothing here removes an observation, "
    "deletes collected history or touches an account, and this system trades nothing on "
    "Polymarket. Removing an observation takes its whole history with it and is an "
    "operator's action in the terminal."
)


def build_server(app) -> FastMCP:
    return _build("polymarket-data", INSTRUCTIONS, lambda mcp: tools.register(mcp, ToolContext(app=app)))


def build_mcp_app(app) -> tuple[FastMCP, ASGIApp]:
    """The streamable-http transport and the server behind it, to be mounted under `/mcp`."""
    return _mount(build_server(app))
