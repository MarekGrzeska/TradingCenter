"""What this module announces on its tool surface: its name, its instructions, and which tools go on
it. Nothing here writes, and the instructions have to say it twice, because a model reading an empty
window guesses otherwise. The mounting is `tc_mcp_kit.mounted_server`."""

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
    "Social-media posts kept as an archive: what was said, when, and what a model made of it. "
    "impact_score is 1..10 and was produced by a model at collection time — it is a stored "
    "reading, not this module's opinion, and a null score means no model has read that post. "
    "Nothing here changes anything: there is no tool that collects on demand, edits or deletes. "
    "Lists carry an excerpt; read_post carries the whole text. Before reporting that nobody "
    "posted anything, call social_archive_status — an empty window is also what a source this "
    "archive has not heard from in hours looks like."
)


def build_server(app) -> FastMCP:
    return _build("social-data", INSTRUCTIONS, lambda mcp: tools.register(mcp, ToolContext(app=app)))


def build_mcp_app(app) -> tuple[FastMCP, ASGIApp]:
    """The streamable-http transport and the server behind it, to be mounted under `/mcp`."""
    return _mount(build_server(app))
