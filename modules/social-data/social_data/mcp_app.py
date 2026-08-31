"""One FastMCP instance, mounted at `/mcp` in this module's own application — the same shape as
`market-data`'s, down to the two production failures that shaped it, written out rather than inherited."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager, nullcontext

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.types import ASGIApp
from tc_mcp_kit.tool_schemas import slim_tool_schemas

from . import tools
from .tools import ToolContext

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
    mcp = FastMCP(
        "social-data",
        instructions=INSTRUCTIONS,
        # Off, explicitly: FastMCP turns DNS-rebinding protection on for a loopback host and then
        # answers 421 to every request. Behind Easy Auth a page cannot mint a token, so it buys nothing.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    tools.register(mcp, ToolContext(app=app))

    # Every tool's schema, minus what pydantic writes for its own sake. The whole set is read by the
    # model in every turn of a conversation, and this is the fourth such set in the system.
    slim_tool_schemas(mcp)

    return mcp


def build_mcp_app(app) -> tuple[FastMCP, ASGIApp]:
    """The streamable-http transport and the server behind it, to be mounted under `/mcp`. Both, because
    the path becomes `/mcp/mcp` unset, and a mounted app's lifespan never runs to start its task group."""
    mcp = build_server(app)
    mcp.settings.streamable_http_path = "/"
    return mcp, mcp.streamable_http_app()


MOUNT_PATH = "/mcp"


def tool_surface_session(app) -> AbstractAsyncContextManager:
    """The session manager's lifetime, held open for as long as the app serves. `nullcontext` when
    nothing was mounted: a suite's own application without a tool surface has nothing to start."""
    mcp = getattr(app.state, "mcp_server", None)
    return nullcontext() if mcp is None else mcp.session_manager.run()


class ToolSurfaceAddress:
    """Makes `/mcp` and `/mcp/` the same address, in front of routing. Starlette answers `/mcp` with a
    307 to `/mcp/`, and an MCP client does not follow a redirect on a POST."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http" and scope.get("path") == MOUNT_PATH:
            with_slash = f"{MOUNT_PATH}/"
            scope = {**scope, "path": with_slash, "raw_path": with_slash.encode()}
        await self._app(scope, receive, send)
