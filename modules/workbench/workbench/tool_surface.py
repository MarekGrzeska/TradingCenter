"""A tool surface of this process's own, for the operator's own MCP client (`operator-mcp-access`): tools alone under
`<prefix>/mcp`, behind a caller record like every package's. The server is built in the lifespan and read off the state
per request, because what it calls through exists only once the lifespan has opened it."""

from __future__ import annotations

from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount
from starlette.types import Receive, Scope, Send
from tc_mcp_kit.mounted_server import MOUNT_PATH, ToolSurfaceAddress, tool_surface_session
from tc_runtime.caller_access import CallerAccess, Record


def create_surface(starting_detail: str) -> Starlette:
    """Mounted at import; `serving` puts the server behind it."""
    surface = Starlette()
    surface.state.starting_detail = starting_detail
    # Tools alone: nothing here is REST, and nothing answers without an identity.
    record = Record(open_paths=frozenset(), rest_paths=(), tools_prefix=MOUNT_PATH, starting_detail=starting_detail)
    surface.router.routes.append(Mount(MOUNT_PATH, app=_ServerOnTheState(surface.state)))
    # In this order, as in every package: the address fix runs before routing, and the caller record before that.
    surface.add_middleware(ToolSurfaceAddress)
    surface.add_middleware(CallerAccess, state=surface.state, record=record)
    return surface


class _ServerOnTheState:
    def __init__(self, state) -> None:
        self._state = state

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        server = getattr(self._state, "mcp_server", None)
        if server is None:
            await JSONResponse({"detail": self._state.starting_detail}, status_code=503)(scope, receive, send)
            return
        await server.session_manager.handle_request(scope, receive, send)


@asynccontextmanager
async def serving(surface: Starlette, server: FastMCP, settings):
    """`CallerAccess` reads the process's own tool list and principal requirement; with no REST path it reads nothing else."""
    surface.state.mcp_server = server
    surface.state.settings = settings
    async with tool_surface_session(surface):
        yield
