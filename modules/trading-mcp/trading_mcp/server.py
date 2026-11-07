"""One FastMCP instance, one transport — and it is the network one. A locally spawned process carries
no caller identity, and `allowed_applications` stops meaning anything once a tool can move money."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp
from tc_entra_auth import EdgeAuth, EdgeConfig, RolePolicy, TokenVerifier
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

LIVE_INSTRUCTIONS = (
    "Tools over capital-gateway's LIVE account — real money, not a demo. Read positions, working orders and "
    "balance, and place, amend or cancel orders on the one account this instance stands on. The gateway holds "
    "each order to its limits — which instruments, and how large one order may be — and refuses one outside "
    "them rather than trimming it. Closing, amending stops and cancelling are never held to the limits. There "
    "is no switching accounts and no balance adjustment here. No price, candle or indicator tool lives here."
)

# Every write tool's description opens with this on the live instance, so a client that reads one tool and not the
# instructions still knows what it is about to move.
LIVE_PREFIX = "LIVE ACCOUNT — REAL MONEY. "
LIVE_ORDER_NOTE = (
    " On this account an order outside the gateway's limits is refused, naming the limit, and never trimmed."
)


def build_server(settings: Settings, gateway: GatewayClient) -> FastMCP:
    live = settings.expected_environment == "live"
    mcp = FastMCP(
        "trading-mcp",
        instructions=LIVE_INSTRUCTIONS if live else INSTRUCTIONS,
        host=settings.trading_mcp_host,
        port=settings.trading_mcp_port,
    )

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    tools.register(mcp, gateway, live=live)
    if live:
        _say_live(mcp)

    # Every tool's schema, minus what pydantic writes for its own sake — 22,6% of what this process
    # announces in every turn of a conversation, and not one field or `required` entry with it.
    slim_tool_schemas(mcp)

    return mcp


def _say_live(mcp: FastMCP) -> None:
    """The tools' own words are written for demo; on the live instance every one says which account it acts on."""
    for tool in mcp._tool_manager.list_tools():
        description = (tool.description or "").replace("the demo account", "the live account")
        description = description.replace("demo account", "live account")
        if tool.annotations is not None and tool.annotations.readOnlyHint is False:
            description = LIVE_PREFIX + description
        if tool.name == "place_order":
            description = description.rstrip() + LIVE_ORDER_NOTE
        tool.description = description


def build_http_app(settings: Settings, gateway: GatewayClient) -> ASGIApp:
    mcp = build_server(settings, gateway)
    guarded = RequireCallerIdentity(
        mcp.streamable_http_app(), settings.require_authenticated_principal
    )
    return EdgeAuth(guarded, edge_config(settings))


def edge_config(settings: Settings) -> EdgeConfig | None:
    """`None` is not a server, and the door stays as the platform left it. With no external caller named there is no
    verifier, so a request carrying the edge marker is refused whatever it presents; with one, the edge admits a
    gateway token of a named application, for an `admin` — a `viewer` has no business with the account."""
    if not settings.server_mode:
        return None
    callers = settings.external_callers
    verifier = None
    if callers:
        assert settings.entra_tenant_id is not None  # the settings refuse external callers without it
        verifier = TokenVerifier(tenant_id=settings.entra_tenant_id, audiences=settings.audiences)
    return EdgeConfig(
        verifier=verifier,
        service_key=settings.capital_gateway_api_key,
        internal_application_id=settings.internal_caller_application_id,
        key_header=GATEWAY_KEY_HEADER.lower().encode(),
        exempt_paths=frozenset({HEALTH_PATH}),
        role_policy=RolePolicy(),
        token_applications=callers,
    )
