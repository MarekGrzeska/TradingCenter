"""One FastMCP instance, mounted at `/mcp` in this module's own application.

The same shape as `market-data`'s, down to the two production failures that shaped it — a
mounted transport whose path doubles, and a mounted lifespan that never runs. Both are
written out below rather than inherited silently, because a module that copies the fix
without the reason loses it at the next edit.

`/health` is left to `routers/meta.py`: the platform's probe reaches this application, not
this route.
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
    "Prediction-market data from Polymarket: search its public database, choose what to "
    "collect, and read what has been collected. Prices are probabilities on 0..1, never "
    "percentages. Three tools change the list of what is collected — track_event, "
    "untrack_event and create_group — and nothing here deletes collected history or "
    "touches an account: this system trades nothing on Polymarket. Deleting collected "
    "data is an operator's action in the terminal."
)


def build_server(app) -> FastMCP:
    mcp = FastMCP(
        "polymarket-data",
        instructions=INSTRUCTIONS,
        # Off, explicitly. FastMCP turns DNS-rebinding protection on whenever its `host` is
        # a loopback one, which it is by default, and then answers `421 Invalid Host header`
        # to every request not addressed to localhost — which, mounted inside this module,
        # is every request there is. The protection guards a server a browser can reach
        # without credentials; this one is behind Easy Auth and this module's own caller
        # record, and a page cannot mint an Entra token for it.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    tools.register(mcp, ToolContext(app=app))

    # Every tool's schema, minus what pydantic writes for its own sake: field titles
    # repeating field names, an `anyOf` of bare types where a type list says the same, and
    # defaults on a reply nobody constructs. The whole set is read by the model in every
    # turn of a conversation, and this is the third such set in the system.
    slim_tool_schemas(mcp)

    return mcp


def build_mcp_app(app) -> tuple[FastMCP, ASGIApp]:
    """The streamable-http transport and the server behind it, to be mounted under `/mcp`.

    Both, because mounting one is not enough:

    * **The path.** `streamable_http_app()` puts its endpoint at
      `settings.streamable_http_path`, `/mcp` by default. Mounted under `/mcp` that becomes
      `/mcp/mcp`, and every caller's configured address answers `307` into a `404`. Set to
      `/` here, so the mount decides the address and nothing else does.
    * **The lifespan.** The Starlette app returned carries a lifespan that starts the
      session manager's task group, and a mounted application's lifespan is never run. So
      the caller gets the server too and runs `session_manager.run()` in its own lifespan.
    """
    mcp = build_server(app)
    mcp.settings.streamable_http_path = "/"
    return mcp, mcp.streamable_http_app()


MOUNT_PATH = "/mcp"


def tool_surface_session(app) -> AbstractAsyncContextManager:
    """The session manager's lifetime, held open for as long as the app serves.

    `nullcontext` when nothing was mounted: the suites that drive the lifespan build their
    own applications, and one without a tool surface has nothing to start.
    """
    mcp = getattr(app.state, "mcp_server", None)
    return nullcontext() if mcp is None else mcp.session_manager.run()


class ToolSurfaceAddress:
    """Makes `/mcp` and `/mcp/` the same address, in front of routing.

    A mount matches `/mcp/...`; a request to `/mcp` itself matches nothing and Starlette
    answers `307` to `/mcp/`. An MCP client posts to the address it was configured with and
    does not follow a redirect on a POST, so that 307 is a dead end — and `/mcp` is the
    address this module publishes.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http" and scope.get("path") == MOUNT_PATH:
            with_slash = f"{MOUNT_PATH}/"
            scope = {**scope, "path": with_slash, "raw_path": with_slash.encode()}
        await self._app(scope, receive, send)
