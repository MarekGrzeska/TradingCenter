"""One FastMCP instance, two transports, one tool surface.

`custom_route` puts `/health` on the same Starlette app `streamable_http_app()` builds,
so the platform that restarts the container on a failed probe can reach it without
opening an MCP session — it does not speak the protocol
(specs/market-mcp-transport, "Zdrowie modułu da się sprawdzić bez sesji MCP").
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from . import resources, tools
from .client import UpstreamClient
from .config import Settings
from .network_identity import RequireCallerIdentity

INSTRUCTIONS = (
    "Read-only tools over market-data's candle archive and indicator catalogue. No "
    "tool here changes state: starting collection on a pair, or deleting one, happens "
    "in the terminal, never through this server."
)


def build_server(settings: Settings, upstream: UpstreamClient) -> FastMCP:
    mcp = FastMCP(
        "market-mcp",
        instructions=INSTRUCTIONS,
        host=settings.mcp_http_host,
        port=settings.mcp_http_port,
    )

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    tools.register(mcp, upstream)
    resources.register(mcp, upstream)

    return mcp


def build_http_app(settings: Settings, upstream: UpstreamClient) -> ASGIApp:
    """The streamable-http transport, wrapped with the caller-identity check —
    stdio has no network caller to check, so `build_server` alone is what it runs
    (specs/market-mcp-transport, "Żądanie z sieci niesie tożsamość wołającego" is
    scoped to "gdy moduł jest wystawiony w sieci").
    """
    mcp = build_server(settings, upstream)
    return RequireCallerIdentity(
        mcp.streamable_http_app(), settings.require_authenticated_principal
    )
