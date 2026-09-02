"""One FastMCP instance mounted at `/mcp` inside a module's own application. Five modules wrote this
out, and the three notes below are why they did: each is a way it went wrong in production, and each
is the kind of thing that gets fixed in one copy. What stays in a module is its name, its
instructions, and which tools it registers."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, nullcontext

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.types import ASGIApp

from .tool_schemas import slim_tool_schemas

MOUNT_PATH = "/mcp"


def build_server(name: str, instructions: str, register: Callable[[FastMCP], None]) -> FastMCP:
    """The server a module publishes. `register` is where the module puts its own tools on it, which
    is the only part of this that was ever different."""
    mcp = FastMCP(
        name,
        instructions=instructions,
        # Off, explicitly: FastMCP turns DNS-rebinding protection on for a loopback host and then
        # answers 421 to every request. Behind Easy Auth a page cannot mint a token, so it buys nothing.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    register(mcp)
    # Every tool's schema, minus what pydantic writes for its own sake: field titles repeating field
    # names, an `anyOf` of bare types where a type list says the same. The whole set is read by the
    # model in every turn of a conversation.
    slim_tool_schemas(mcp)
    return mcp


def build_mcp_app(server: FastMCP) -> tuple[FastMCP, ASGIApp]:
    """The streamable-http transport and the server behind it, to be mounted under `/mcp`. Both,
    because the path becomes `/mcp/mcp` unset, and a mounted app's lifespan never runs to start its
    task group."""
    server.settings.streamable_http_path = "/"
    return server, server.streamable_http_app()


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
