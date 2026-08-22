"""One FastMCP instance, mounted at `/mcp` in this module's own application.

The three notes below are market-data's, kept because they are the three ways this went
wrong in production on 19 August 2026 and none of them is obvious from the library:

* **The path.** `streamable_http_app()` puts its endpoint at
  `settings.streamable_http_path`, which is `/mcp` by default. Mounted under `/mcp` that
  becomes `/mcp/mcp`, and the address every caller was configured with answers `307` into
  a `404`. Set to `/` here, so the mount decides the address and nothing else does.
* **The lifespan.** A mounted application's lifespan is never run — only the outermost one
  is — so the task group the transport dispatches into has to be started by the lifespan
  of the app that mounted it (`tool_surface_session`, called from `app.py`).
* **The trailing slash.** A mount matches `/mcp/...`; a request to `/mcp` itself matches
  nothing and Starlette answers `307`. An MCP client posts to the address it was
  configured with and does not follow a redirect on a POST (`ToolSurfaceAddress`).
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager, nullcontext

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.types import ASGIApp
from tc_mcp_kit.tool_schemas import slim_tool_schemas

from . import tools
from .tools import ToolContext

INSTRUCTIONS = (
    "Read-only tools over the strategy platform: which strategies are watching what, and "
    "what they decided. No tool here changes anything — activating a strategy, writing a "
    "parameter set or running a backtest happens over this module's REST contract, never "
    "through this server. This module never touches an account: a setup here is a "
    "reading, not an order."
)


def build_server(app) -> FastMCP:
    mcp = FastMCP(
        "strategy",
        instructions=INSTRUCTIONS,
        # Off, explicitly, and the explicitness is the point: FastMCP turns DNS-rebinding
        # protection *on* whenever its `host` is a loopback one, and then answers `421
        # Invalid Host header` to every request not addressed to localhost — which,
        # mounted inside this module, is every request there is. What the check would buy
        # here is nothing: this surface is behind Easy Auth and behind this module's own
        # caller record, so a page cannot mint a token for it.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    tools.register(mcp, ToolContext(app=app))

    # Every tool's schema, minus what pydantic writes for its own sake: field titles
    # repeating field names, an `anyOf` of bare types where a type list says the same.
    slim_tool_schemas(mcp)

    return mcp


def build_mcp_app(app) -> tuple[FastMCP, ASGIApp]:
    """The streamable-http transport and the server behind it, to be mounted under `/mcp`."""
    mcp = build_server(app)
    mcp.settings.streamable_http_path = "/"
    return mcp, mcp.streamable_http_app()


MOUNT_PATH = "/mcp"


def tool_surface_session(app) -> AbstractAsyncContextManager:
    """The session manager's own lifetime, held open for as long as the app serves.

    `nullcontext` when nothing was mounted: the suites that drive the lifespan build their
    own applications, and one without a tool surface has nothing to start.
    """
    mcp = getattr(app.state, "mcp_server", None)
    return nullcontext() if mcp is None else mcp.session_manager.run()


class ToolSurfaceAddress:
    """Makes `/mcp` and `/mcp/` the same address, in front of routing."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http" and scope.get("path") == MOUNT_PATH:
            with_slash = f"{MOUNT_PATH}/"
            scope = {**scope, "path": with_slash, "raw_path": with_slash.encode()}
        await self._app(scope, receive, send)
