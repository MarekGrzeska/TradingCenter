"""One FastMCP instance, one transport — and it is the network one.

Unlike `market-mcp`, which also wires up `stdio` for a client on a desk, this module
publishes nothing over a locally spawned process: a process carries no caller identity
of its own, and `allowed_applications` would stop meaning anything the moment a tool
here can move money (specs/trading-mcp-transport, "Moduł wystawia jeden transport i
jest nim transport sieciowy").

`custom_route` puts `/health` on the same Starlette app `streamable_http_app()`
builds, the same mechanism `market_mcp/server.py` uses for the same reason: the
platform that restarts the container on a failed probe does not speak MCP.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp
from tc_mcp_kit.network_identity import RequireCallerIdentity
from tc_mcp_kit.tool_schemas import slim_tool_schemas

from . import tools
from .client import GatewayClient
from .config import Settings

INSTRUCTIONS = (
    "Tools over capital-gateway's demo account: read positions, working orders and "
    "balance, and place, amend or cancel orders. No price, candle or indicator tool "
    "lives here — that is market-mcp's archive, and this module has none of its own."
)


def build_server(settings: Settings, gateway: GatewayClient) -> FastMCP:
    mcp = FastMCP(
        "trading-mcp",
        instructions=INSTRUCTIONS,
        host=settings.trading_mcp_host,
        port=settings.trading_mcp_port,
    )

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    tools.register(mcp, gateway)

    # Every tool's schema, minus what pydantic writes for its own sake: field titles
    # repeating field names, an `anyOf` of bare types where a type list says the same, and
    # defaults on a reply nobody constructs. 22,6% of what this process announces in every
    # turn of a conversation, and not one field, type or `required` entry with it
    # (specs/trading-mcp-tools, "Powierzchnia narzędzi ma zapisany sufit").
    slim_tool_schemas(mcp)

    return mcp


def build_http_app(settings: Settings, gateway: GatewayClient) -> ASGIApp:
    mcp = build_server(settings, gateway)
    return RequireCallerIdentity(
        mcp.streamable_http_app(), settings.require_authenticated_principal
    )
