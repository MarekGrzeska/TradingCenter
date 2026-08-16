"""Who gets which tools, and when a run is refused before an agent is called."""

from __future__ import annotations

import pytest

from teams.contract import AgentDefinition, TeamDefinition, TeamEdge
from teams.tools import (
    ToolAccessError,
    ToolNoLongerAnnounced,
    ToolServer,
    ToolServerUnavailable,
    plan_tools,
)

from .mcp_stand_in import free_port, serving, settings_for


def agent(key: str, tools: list[str]) -> AgentDefinition:
    return AgentDefinition(
        key=key, role=f"{key} role", prompt="do the thing", model_id="gpt-5.6-luna", tools=tools
    )


def team(*agents: AgentDefinition, edges: list[TeamEdge] | None = None) -> TeamDefinition:
    return TeamDefinition(agents=list(agents), edges=edges or [])


async def test_an_agent_gets_the_tools_the_definition_named_and_no_others() -> None:
    """specs/teams-tool-access, "Agent dostaje narzędzia wskazane w definicji, a nie
    wszystkie". The server publishes three; the reader is assigned two and the writer one."""
    definition = team(
        agent("reader", ["get_last_price", "read_indicators"]),
        agent("writer", ["list_tracked_pairs"]),
        edges=[TeamEdge(from_="reader", to="writer")],
    )

    async with serving() as url:
        server = ToolServer(settings_for(url))
        try:
            plan = await plan_tools(definition, server)
        finally:
            await server.aclose()

    assert [tool.name for tool in plan.for_agent("reader")] == [
        "get_last_price",
        "read_indicators",
    ]
    assert [tool.name for tool in plan.for_agent("writer")] == ["list_tracked_pairs"]


async def test_the_order_is_the_definitions_own() -> None:
    definition = team(agent("reader", ["read_indicators", "get_last_price"]))

    async with serving() as url:
        server = ToolServer(settings_for(url))
        try:
            plan = await plan_tools(definition, server)
        finally:
            await server.aclose()

    assert [tool.name for tool in plan.for_agent("reader")] == [
        "read_indicators",
        "get_last_price",
    ]


async def test_descriptors_come_from_the_session_not_from_the_revision() -> None:
    definition = team(agent("reader", ["get_last_price"]))

    async with serving() as url:
        server = ToolServer(settings_for(url))
        try:
            plan = await plan_tools(definition, server)
        finally:
            await server.aclose()

    tool = plan.for_agent("reader")[0]
    assert "bid side" in tool.description
    assert tool.input_schema["properties"]["symbol"]["type"] == "string"


async def test_a_tool_the_server_stopped_announcing_refuses_the_run() -> None:
    """specs/teams-tool-access, "Narzędzie znika po stronie serwera": named, refused, and
    the revision left alone."""
    definition = team(
        agent("reader", ["get_last_price", "read_indicators"]),
        agent("writer", ["list_tracked_pairs"]),
        edges=[TeamEdge(from_="reader", to="writer")],
    )

    async with serving(tools=("get_last_price", "list_tracked_pairs")) as url:
        server = ToolServer(settings_for(url))
        try:
            with pytest.raises(ToolNoLongerAnnounced) as raised:
                await plan_tools(definition, server)
        finally:
            await server.aclose()

    message = str(raised.value)
    assert "'read_indicators'" in message
    # The agent, too: the operator's next move is to open that agent's panel.
    assert "'reader'" in message
    assert "still readable" in message
    # And it is an access refusal like the other one, so a run start catches one type.
    assert isinstance(raised.value, ToolAccessError)


async def test_a_team_that_assigns_tools_is_refused_when_the_server_is_unreachable() -> None:
    """specs/teams-tool-access, "Serwer narzędzi nieosiągalny przy uruchomieniu"."""
    definition = team(agent("reader", ["get_last_price"]))
    server = ToolServer(settings_for(f"http://127.0.0.1:{free_port()}"))
    try:
        with pytest.raises(ToolServerUnavailable):
            await plan_tools(definition, server)
    finally:
        await server.aclose()


async def test_a_team_that_assigns_tools_is_refused_when_no_server_is_configured() -> None:
    definition = team(agent("reader", ["get_last_price"]))
    server = ToolServer(settings_for(None))
    try:
        with pytest.raises(ToolServerUnavailable) as raised:
            await plan_tools(definition, server)
    finally:
        await server.aclose()

    assert "MARKET_MCP_URL is unset" in str(raised.value)


async def test_a_team_with_no_tools_runs_though_the_server_is_unreachable() -> None:
    """specs/teams-tool-access, "Zespół, w którym nikt nie ma narzędzi". The server is not
    contacted at all — an outage elsewhere must not stop a run that never needed it."""
    definition = team(
        agent("thinker", []),
        agent("critic", []),
        edges=[TeamEdge(from_="thinker", to="critic")],
    )
    server = ToolServer(settings_for(f"http://127.0.0.1:{free_port()}"))
    try:
        plan = await plan_tools(definition, server)
    finally:
        await server.aclose()

    assert plan.for_agent("thinker") == ()
    assert plan.for_agent("critic") == ()


async def test_a_team_with_no_tools_runs_with_no_server_configured() -> None:
    definition = team(agent("thinker", []))
    server = ToolServer(settings_for(None))
    try:
        plan = await plan_tools(definition, server)
    finally:
        await server.aclose()

    assert plan.for_agent("thinker") == ()


async def test_an_agent_carrying_no_tools_beside_one_that_does_gets_none() -> None:
    definition = team(
        agent("reader", ["get_last_price"]),
        agent("thinker", []),
        edges=[TeamEdge(from_="reader", to="thinker")],
    )

    async with serving() as url:
        server = ToolServer(settings_for(url))
        try:
            plan = await plan_tools(definition, server)
        finally:
            await server.aclose()

    assert [tool.name for tool in plan.for_agent("reader")] == ["get_last_price"]
    assert plan.for_agent("thinker") == ()


async def test_an_unknown_agent_key_is_a_programming_error() -> None:
    definition = team(agent("reader", []))
    server = ToolServer(settings_for(None))
    try:
        plan = await plan_tools(definition, server)
    finally:
        await server.aclose()

    # Not an empty tuple: that reads as "assigned nothing", which is a real state this
    # module has to be able to report truthfully.
    with pytest.raises(KeyError):
        plan.for_agent("nobody")
