"""The FastMCP instances over the team tools: one with no transport, which the conversation calls as a registry, and one
the operator's own MCP client reaches over the network (`operator-mcp-access`), acting for the person the door read
off that client's token."""

from __future__ import annotations

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from tc_mcp_kit.tool_call import request_header
from tc_mcp_kit.tool_schemas import slim_tool_schemas

from . import tools
from .client import TeamsClient
from .operator import carrying

# Written by the door after it verified the caller's token (`tc-entra-auth`), and removed first whatever the client sent.
PERSON_HEADER = "x-ms-client-principal-id"

log = logging.getLogger(__name__)

INSTRUCTIONS = (
    "Tools over the operator's own team catalogue: list and read teams, create one, "
    "revise it into a new revision, run it, read what a run did and what it cost, and "
    "put it on a schedule or a market-condition trigger. Everything acts in the name of "
    "the operator whose chat this is — what you create here is theirs, appears in their "
    "Teams tab, and is spent against their limits. Nothing here reads the market: that "
    "is the archive's own tool surface, and this one has none of its own."
)


def build_server(teams: TeamsClient) -> FastMCP:
    return _furnished(FastMCP("teams-tools", instructions=INSTRUCTIONS), teams)


def build_network_server(teams: TeamsClient) -> FastMCP:
    """The same tools for a caller over the network. Without an authenticator in front (local work) nobody can be named,
    and the call carries no identity, exactly as the conversation's does there."""
    return _furnished(
        _ActingForTheRequest(
            "teams-tools",
            instructions=INSTRUCTIONS,
            operator_identity_optional=teams.operator_identity_optional,
            # Off, as in `tc_mcp_kit.mounted_server`: FastMCP turns DNS-rebinding protection on for its loopback default
            # host and then answers 421 to every request that names the real one.
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        ),
        teams,
    )


def _furnished(mcp: FastMCP, teams: TeamsClient) -> FastMCP:
    tools.register(mcp, teams)

    # Every tool's schema, minus what pydantic writes for its own sake — 22,6% of what this surface
    # announces in every turn of a conversation, and not one field or `required` entry with it.
    slim_tool_schemas(mcp)

    return mcp


class _ActingForTheRequest(FastMCP):
    """Sets the operator for one tool call from the request that carried it. Here and not in a middleware around the
    request: in stateful streamable-http the tool runs in the session's task, which a context variable set around the
    HTTP request never reaches."""

    def __init__(self, *args: Any, operator_identity_optional: bool, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._operator_identity_optional = operator_identity_optional

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        principal = None if self._operator_identity_optional else request_header(PERSON_HEADER)
        with carrying(principal):
            return await super().call_tool(name, arguments)


def say_whose_name_the_tools_act_in(operator_identity_optional: bool) -> None:
    """Which of the two states this process came up in, said once at startup, because the state where tools work with
    no operator behind them MUST NOT be inferred from an absence of refusals. In a log line: a sentence per answer costs tokens."""
    if operator_identity_optional:
        log.info(
            "no authenticator stands in front of this process "
            "(REQUIRE_AUTHENTICATED_PRINCIPAL=false), so no layer could identify an "
            "operator: the team tools act carrying no identity, and what they create "
            "belongs to whatever principal the teams routes give an unauthenticated request"
        )
        return
    log.info(
        "the team tools act in the operator's own name, taken from the request being "
        "served: a turn reaching them without one is refused"
    )
