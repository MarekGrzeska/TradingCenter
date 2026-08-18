"""One FastMCP instance, one transport — and it is the network one.

Unlike `market-mcp`, which also wires up `stdio` for a client on a desk, this module
publishes nothing over a locally spawned process. A spawned process carries no caller
identity, and the tools here create teams and start runs in an operator's name
(specs/teams-mcp-transport, "Jeden transport, wybrany bez pytania wołającego").

`custom_route` puts `/health` on the same Starlette app `streamable_http_app()` builds,
the same mechanism both other MCP modules use for the same reason: the platform that
restarts the container on a failed probe does not speak MCP.
"""

from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp
from tc_runtime.network_identity import RequireCallerIdentity

from . import tools
from .client import TeamsClient
from .config import Settings

log = logging.getLogger(__name__)

INSTRUCTIONS = (
    "Tools over the operator's own team catalogue: list and read teams, create one, "
    "revise it into a new revision, run it, read what a run did and what it cost, and "
    "put it on a schedule or a market-condition trigger. Everything acts in the name of "
    "the operator whose chat this is — what you create here is theirs, appears in their "
    "Teams tab, and is spent against their limits. Nothing here reads the market: that "
    "is market-mcp's archive, and this module has none of its own."
)


def build_server(settings: Settings, teams: TeamsClient) -> FastMCP:
    mcp = FastMCP(
        "teams-mcp",
        instructions=INSTRUCTIONS,
        host=settings.teams_mcp_host,
        port=settings.teams_mcp_port,
    )

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_request: Request) -> JSONResponse:
        # Says that the process answers, and nothing else — no count of teams, no
        # operator, no word about whether `teams` itself is up (specs/teams-mcp-transport,
        # "Jedno wejście odpowiada bez poświadczenia").
        return JSONResponse({"status": "ok"})

    tools.register(mcp, teams)

    return mcp


def build_http_app(settings: Settings, teams: TeamsClient) -> ASGIApp:
    _say_whose_name_the_tools_act_in(settings)
    mcp = build_server(settings, teams)
    return RequireCallerIdentity(
        mcp.streamable_http_app(), settings.require_authenticated_principal
    )


def _say_whose_name_the_tools_act_in(settings: Settings) -> None:
    """Which of the two states this process came up in, said once, at startup.

    The state where tools work without an operator behind them MUST NOT be one an operator
    infers from an absence of refusals (specs/teams-mcp-authorship, "Moduł mówi, w którym
    stanie wstał"). Said in a log line rather than appended to every tool answer: a
    sentence in each result is paid for in model tokens on every call, and it would make a
    local answer differ in content from the deployed one — the one thing a local run exists
    to compare (design.md, "Jedna linia przy starcie").
    """
    if settings.operator_identity_optional:
        log.info(
            "no authenticator stands in front of this module "
            "(REQUIRE_AUTHENTICATED_PRINCIPAL=false) and teams is on this machine (%s), so "
            "no layer could issue an operator token: tools act carrying no identity, and "
            "what they create belongs to whatever principal teams gives an unauthenticated "
            "request",
            settings.teams_url,
        )
        return
    log.info(
        "tools act in the operator's own name, carried per call: a call reaching this "
        "module without one is refused (teams at %s, authenticator in front: %s)",
        settings.teams_url,
        settings.require_authenticated_principal,
    )
