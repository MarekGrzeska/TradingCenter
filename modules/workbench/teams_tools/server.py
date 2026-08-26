"""One FastMCP instance and no transport at all: `FastMCP` is kept because it is the tool registry, the schema generator
and the annotation carrier. What went with the process is the HTTP app, the caller-identity check and `/health`."""

from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP
from tc_mcp_kit.tool_schemas import slim_tool_schemas

from . import tools
from .client import TeamsClient

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
    mcp = FastMCP("teams-tools", instructions=INSTRUCTIONS)

    tools.register(mcp, teams)

    # Every tool's schema, minus what pydantic writes for its own sake — 22,6% of what this surface
    # announces in every turn of a conversation, and not one field or `required` entry with it.
    slim_tool_schemas(mcp)

    return mcp


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
