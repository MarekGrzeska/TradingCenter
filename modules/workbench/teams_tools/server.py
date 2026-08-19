"""One FastMCP instance, and no transport at all.

`FastMCP` is kept even though nothing is served over a socket any more, and the reason is
that a transport was never what it was for here: it is the tool registry, the schema
generator and the annotation carrier. Registering with `@mcp.tool` is what turns a typed
Python function into a description, an input schema and a `readOnlyHint` the model reads —
and `slim_tool_schemas` is what keeps the whole of that under the ceiling this surface has
a written one for.

What went with the process: `streamable_http_app()`, `RequireCallerIdentity` (there is no
caller across a network to identify), `/health` (`workbench/app.py` publishes the one this
process has) and the host and port it used to bind.
"""

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

    # Every tool's schema, minus what pydantic writes for its own sake: field titles
    # repeating field names, an `anyOf` of bare types where a type list says the same, and
    # defaults on a reply nobody constructs. 22,6% of what this surface announces in every
    # turn of a conversation, and not one field, type or `required` entry with it
    # ("Powierzchnia narzędzi ma zapisany sufit").
    slim_tool_schemas(mcp)

    return mcp


def say_whose_name_the_tools_act_in(operator_identity_optional: bool) -> None:
    """Which of the two states this process came up in, said once, at startup.

    The state where tools work without an operator behind them MUST NOT be one an operator
    infers from an absence of refusals ("Moduł mówi, w którym stanie wstał"). Said in a log
    line rather than appended to every tool answer: a sentence in each result is paid for
    in model tokens on every call, and it would make a local answer differ in content from
    the deployed one — the one thing a local run exists to compare.

    One condition rather than two: the second was whether the catalogue was reached at a
    remote address, and there is no address now.
    """
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
