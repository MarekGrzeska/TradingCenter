"""One FastMCP instance, one transport — and it is the network one. A locally spawned process carries
no caller identity, and `allowed_applications` stops meaning anything once a tool can move money."""

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

    # Every tool's schema, minus what pydantic writes for its own sake — 22,6% of what this process
    # announces in every turn of a conversation, and not one field or `required` entry with it.
    slim_tool_schemas(mcp)

    return mcp


def build_http_app(settings: Settings, gateway: GatewayClient) -> ASGIApp:
    mcp = build_server(settings, gateway)
    return RequireCallerIdentity(
        mcp.streamable_http_app(), settings.require_authenticated_principal
    )
