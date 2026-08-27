"""One FastMCP instance, mounted at `/mcp` in this module's own application. A separate process until
19 August 2026; what it lost is the scaffolding of that separation, not a tool or a ceiling."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager, nullcontext

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.types import ASGIApp
from tc_mcp_kit.tool_schemas import slim_tool_schemas

from . import tools
from .tools import ToolContext

INSTRUCTIONS = (
    "Read-only tools over this archive's candles and indicator catalogue. No tool here "
    "changes state: starting collection on a pair, or deleting one, happens in the "
    "terminal, never through this server."
)


def build_server(app) -> FastMCP:
    mcp = FastMCP(
        "market-data",
        instructions=INSTRUCTIONS,
        # Off, explicitly: FastMCP turns DNS-rebinding protection on for a loopback host and then
        # answers 421 to every request. Behind Easy Auth a page cannot mint a token, so it buys nothing.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    tools.register(mcp, ToolContext(app=app))

    # Every tool's schema, minus what pydantic writes for its own sake — 22,6% of what this process
    # announces in every turn of a conversation, and not one field or `required` entry with it.
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
    """The session manager's own lifetime, held open for as long as the app serves: a mounted app's
    lifespan never runs, so the task group must be started by the app that mounted it."""
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
