"""One FastMCP instance, mounted at `/mcp` in this module's own application.

It was a separate process until 19 August 2026, and what it lost in becoming a route is
the scaffolding of that separation: an HTTP client to this module, a committed copy of
this module's schema, and the script that policed the copy. What it kept is every tool,
every ceiling and every sentence about uncertainty.

`/health` is left to `routers/meta.py`: the platform's probe reaches this application, not
this route, and one module answering two health paths is one more thing to keep in step.
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
    "Read-only tools over this archive's candles and indicator catalogue. No tool here "
    "changes state: starting collection on a pair, or deleting one, happens in the "
    "terminal, never through this server."
)


def build_server(app) -> FastMCP:
    mcp = FastMCP(
        "market-data",
        instructions=INSTRUCTIONS,
        # Off, explicitly, and the explicitness is the point: FastMCP turns DNS-rebinding
        # protection *on* whenever its `host` is a loopback one, which it is by default —
        # and then answers `421 Invalid Host header` to every request not addressed to
        # localhost. Mounted inside this module that is every request there is, including
        # the two callers' own (production, 19 August 2026).
        #
        # The protection guards a server a browser can reach without credentials. This
        # surface is behind Easy Auth and behind this module's own caller record: a page
        # cannot mint an Entra token for it, so what the check would buy here is nothing,
        # and what it costs is the whole route.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    tools.register(mcp, ToolContext(app=app))

    # Every tool's schema, minus what pydantic writes for its own sake: field titles
    # repeating field names, an `anyOf` of bare types where a type list says the same, and
    # defaults on a reply nobody constructs. 22,6% of what this process announces in every
    # turn of a conversation, and not one field, type or `required` entry with it
    # (specs/market-data-tools, "Powierzchnia narzędzi ma zapisany sufit").
    slim_tool_schemas(mcp)

    return mcp


def build_mcp_app(app) -> tuple[FastMCP, ASGIApp]:
    """The streamable-http transport and the server behind it, to be mounted under `/mcp`.

    Both, because mounting one of these is not enough on its own — and this signature is
    written from the two ways that went wrong in production on 19 August 2026:

    * **The path.** `streamable_http_app()` puts its endpoint at `settings.
      streamable_http_path`, which is `/mcp` by default. Mounted under `/mcp` that becomes
      `/mcp/mcp`, and the address every caller was configured with answered `307` into a
      `404`. Set to `/` here, so the mount decides the address and nothing else does.
    * **The lifespan.** The Starlette app this returns carries a lifespan that starts the
      session manager's task group, and a mounted application's lifespan is never run —
      only the outermost one is. Every request then reached the transport and died on
      `RuntimeError: Task group is not initialized`. So the caller gets the server too and
      runs `session_manager.run()` inside its own lifespan (`app.py`).

    Unwrapped by anything here: the caller-identity check is one layer in front of the
    whole application (`caller_access.py`), because this module has a REST surface beside
    this one and the two need one answer to "who is calling", not two.
    """
    mcp = build_server(app)
    mcp.settings.streamable_http_path = "/"
    return mcp, mcp.streamable_http_app()


MOUNT_PATH = "/mcp"


def tool_surface_session(app) -> AbstractAsyncContextManager:
    """The session manager's own lifetime, to be held open for as long as the app serves.

    A mounted application's lifespan is never run — only the outermost one is — so the task
    group the streamable-http transport dispatches into has to be started by the lifespan of
    the app that mounted it. Without this every tool call answered `RuntimeError: Task group
    is not initialized`, which is what production did on 19 August 2026.

    `nullcontext` when nothing was mounted: the suites that drive the lifespan build their
    own applications, and one without a tool surface has nothing to start.
    """
    mcp = getattr(app.state, "mcp_server", None)
    return nullcontext() if mcp is None else mcp.session_manager.run()


class ToolSurfaceAddress:
    """Makes `/mcp` and `/mcp/` the same address, in front of routing.

    A mount matches `/mcp/...`; a request to `/mcp` itself matches nothing, and Starlette's
    router answers it with a `307` to `/mcp/`. An MCP client posts to the address it was
    configured with and does not follow a redirect on a POST, so that 307 is a dead end —
    which is what `agent` and `teams` met on 19 August 2026, both configured with `/mcp`
    because `/mcp` is the address this module publishes.

    In front of the router rather than inside the mounted app, because the redirect happens
    before the mount is ever consulted. Eight lines rather than a trailing slash in three
    `.env` files and two Terraform settings: the address in those files is the one a person
    would write, and this is the module's own job.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http" and scope.get("path") == MOUNT_PATH:
            with_slash = f"{MOUNT_PATH}/"
            scope = {**scope, "path": with_slash, "raw_path": with_slash.encode()}
        await self._app(scope, receive, send)
