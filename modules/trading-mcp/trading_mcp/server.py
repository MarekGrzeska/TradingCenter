"""One FastMCP instance, one transport — and it is the network one. A locally spawned process carries
no caller identity, and `allowed_applications` stops meaning anything once a tool can move money."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp
from tc_entra_auth import EdgeAuth, EdgeConfig
from tc_mcp_kit.network_identity import RequireCallerIdentity
from tc_mcp_kit.tool_schemas import slim_tool_schemas

from . import tools
from .client import GATEWAY_KEY_HEADER, GatewayClient
from .config import Settings

HEALTH_PATH = "/health"

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
    guarded = RequireCallerIdentity(
        mcp.streamable_http_app(), settings.require_authenticated_principal
    )
    return EdgeAuth(guarded, edge_config(settings))


def edge_config(settings: Settings) -> EdgeConfig | None:
    """`None` is not a server, and the door stays as the platform left it. A server has no verifier at all: this
    module is not published at the edge, so a request carrying the edge marker is refused whatever it presents."""
    if not settings.server_mode:
        return None
    return EdgeConfig(
        verifier=None,
        service_key=settings.capital_gateway_api_key,
        internal_application_id=settings.internal_caller_application_id,
        key_header=GATEWAY_KEY_HEADER.lower().encode(),
        exempt_paths=frozenset({HEALTH_PATH}),
    )
