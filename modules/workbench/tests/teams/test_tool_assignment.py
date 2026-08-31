"""Who gets which tools, and when a run is refused before an agent is called."""

from __future__ import annotations

import pytest

from teams.contract import AgentDefinition, TeamDefinition, TeamEdge
from teams.tools import (
    MEMORY_TOOL_NAMES,
    ToolAccessError,
    ToolNameCollision,
    ToolNoLongerAnnounced,
    ToolServerRegistry,
    ToolServerUnavailable,
    announced_snapshot,
    plan_tools,
)

from .mcp_stand_in import free_port, serving, settings_for


def agent(key: str, tools: list[str]) -> AgentDefinition:
    return AgentDefinition(
        key=key, role=f"{key} role", prompt="do the thing", model_id="gpt-5.6-luna", tools=tools
    )


def team(*agents: AgentDefinition, edges: list[TeamEdge] | None = None) -> TeamDefinition:
    return TeamDefinition(agents=list(agents), edges=edges or [])


def _registry(url: str | None, **overrides) -> ToolServerRegistry:
    return ToolServerRegistry.from_settings(settings_for(url, **overrides))


async def test_an_agent_gets_the_tools_the_definition_named_and_no_others() -> None:
    """specs/teams-tool-access, "Agent dostaje narzędzia wskazane w definicji, a nie
    wszystkie". The server publishes three; the reader is assigned two and the writer one."""
    definition = team(
        agent("reader", ["get_last_price", "read_indicators"]),
        agent("writer", ["list_tracked_pairs"]),
        edges=[TeamEdge(from_="reader", to="writer")],
    )

    async with serving() as url:
        registry = _registry(url)
        try:
            plan = await plan_tools(definition, registry)
        finally:
            await registry.aclose()

    assert [tool.name for tool in plan.for_agent("reader")] == [
        "get_last_price",
        "read_indicators",
    ]
    assert [tool.name for tool in plan.for_agent("writer")] == ["list_tracked_pairs"]


async def test_the_order_is_the_definitions_own() -> None:
    definition = team(agent("reader", ["read_indicators", "get_last_price"]))

    async with serving() as url:
        registry = _registry(url)
        try:
            plan = await plan_tools(definition, registry)
        finally:
            await registry.aclose()

    assert [tool.name for tool in plan.for_agent("reader")] == [
        "read_indicators",
        "get_last_price",
    ]


async def test_descriptors_come_from_the_session_not_from_the_revision() -> None:
    definition = team(agent("reader", ["get_last_price"]))

    async with serving() as url:
        registry = _registry(url)
        try:
            plan = await plan_tools(definition, registry)
        finally:
            await registry.aclose()

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
        registry = _registry(url)
        try:
            with pytest.raises(ToolNoLongerAnnounced) as raised:
                await plan_tools(definition, registry)
        finally:
            await registry.aclose()

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
    registry = _registry(f"http://127.0.0.1:{free_port()}")
    try:
        with pytest.raises(ToolServerUnavailable):
            await plan_tools(definition, registry)
    finally:
        await registry.aclose()


async def test_a_team_that_assigns_tools_is_refused_when_no_server_is_configured() -> None:
    """The refusal has to name the server that is missing, which is why it is no longer decided by "is
    anything configured": a source this process serves itself is always configured."""
    definition = team(agent("reader", ["get_last_price"]))
    registry = _registry(None)
    try:
        with pytest.raises(ToolServerUnavailable) as raised:
            await plan_tools(definition, registry)
    finally:
        await registry.aclose()

    message = str(raised.value)
    assert "'get_last_price'" in message
    assert "market-mcp" in message and "trading-mcp" in message
    assert "not configured" in message


async def test_a_team_with_no_tools_runs_though_the_server_is_unreachable() -> None:
    """specs/teams-tool-access, "Zespół, w którym nikt nie ma narzędzi". No server is
    contacted at all — an outage elsewhere must not stop a run that never needed it."""
    definition = team(
        agent("thinker", []),
        agent("critic", []),
        edges=[TeamEdge(from_="thinker", to="critic")],
    )
    registry = _registry(f"http://127.0.0.1:{free_port()}")
    try:
        plan = await plan_tools(definition, registry)
    finally:
        await registry.aclose()

    assert plan.for_agent("thinker") == ()
    assert plan.for_agent("critic") == ()


async def test_a_team_with_no_tools_runs_with_no_server_configured() -> None:
    definition = team(agent("thinker", []))
    registry = _registry(None)
    try:
        plan = await plan_tools(definition, registry)
    finally:
        await registry.aclose()

    assert plan.for_agent("thinker") == ()


async def test_an_agent_carrying_no_tools_beside_one_that_does_gets_none() -> None:
    definition = team(
        agent("reader", ["get_last_price"]),
        agent("thinker", []),
        edges=[TeamEdge(from_="reader", to="thinker")],
    )

    async with serving() as url:
        registry = _registry(url)
        try:
            plan = await plan_tools(definition, registry)
        finally:
            await registry.aclose()

    assert [tool.name for tool in plan.for_agent("reader")] == ["get_last_price"]
    assert plan.for_agent("thinker") == ()


async def test_announced_snapshot_names_the_servers_own_tools() -> None:
    """The save-time shape (`validation.py` checks against this), and its own
    registry: names by server, because a save has nothing to call."""
    async with serving(tools=("get_last_price", "read_indicators")) as url:
        snapshot = await announced_snapshot(settings_for(url))

    assert {"get_last_price", "read_indicators"} <= set(snapshot.by_name)
    assert snapshot.by_name["get_last_price"] == ["market-mcp"]
    assert snapshot.unreachable == []


async def test_announced_snapshot_carries_the_tools_this_process_serves_itself() -> None:
    """Announcing them touches no database — which is the whole reason the save path can
    build a registry out of settings alone and still publish these names."""
    snapshot = await announced_snapshot(settings_for(None))

    assert MEMORY_TOOL_NAMES <= set(snapshot.by_name)
    assert snapshot.by_name["memory_read"] == ["team-memory"]


async def test_announced_snapshot_says_which_servers_have_no_address() -> None:
    # It no longer answers `None` for "nothing is configured": there is always a source
    # announcing something. The narrower claim the `None` used to make is this field.
    snapshot = await announced_snapshot(settings_for(None))

    assert snapshot.unconfigured == (
        "market-mcp",
        "polymarket-mcp",
        "social-mcp",
        "telegram-mcp",
        "trading-mcp",
    )
    assert snapshot.configured_servers == ()
    assert snapshot.unreachable == []


async def test_announced_snapshot_names_an_unreachable_configured_server() -> None:
    snapshot = await announced_snapshot(settings_for(f"http://127.0.0.1:{free_port()}"))

    assert set(snapshot.by_name) == set(MEMORY_TOOL_NAMES)
    assert snapshot.unreachable == ["market-mcp"]
    assert snapshot.configured_servers == ("market-mcp",)


async def test_an_unknown_agent_key_is_a_programming_error() -> None:
    definition = team(agent("reader", []))
    registry = _registry(None)
    try:
        plan = await plan_tools(definition, registry)
    finally:
        await registry.aclose()

    # Not an empty tuple: that reads as "assigned nothing", which is a real state this
    # module has to be able to report truthfully.
    with pytest.raises(KeyError):
        plan.for_agent("nobody")



async def test_an_unreachable_second_server_does_not_stop_a_team_that_never_needed_it() -> None:
    """specs/teams-tool-access, "Nieosiągalny jest tylko serwer, z którego nikt nic nie
    ma": the team's only assigned tool comes from the server that answers."""
    definition = team(agent("reader", ["get_last_price"]))

    async with serving(tools=("get_last_price",)) as market_url:
        registry = _registry(market_url, trading_mcp_url=f"http://127.0.0.1:{free_port()}")
        try:
            plan = await plan_tools(definition, registry)
        finally:
            await registry.aclose()

    assert [tool.name for tool in plan.for_agent("reader")] == ["get_last_price"]


async def test_a_name_two_servers_both_announce_refuses_the_run_naming_both() -> None:
    """specs/teams-tool-access, "Ta sama nazwa narzędzia z dwóch serwerów jest
    odmową"."""
    definition = team(agent("trader", ["place_order"]))

    def one_tool(mcp) -> None:
        @mcp.tool(name="place_order", description="places an order")
        def place_order() -> str:  # pragma: no cover - never called
            return "unused"

    async with serving(build=one_tool) as market_url, serving(build=one_tool) as trading_url:
        registry = _registry(market_url, trading_mcp_url=trading_url)
        try:
            with pytest.raises(ToolNameCollision) as raised:
                await plan_tools(definition, registry)
        finally:
            await registry.aclose()

    message = str(raised.value)
    assert "'place_order'" in message
    assert "market-mcp" in message
    assert "trading-mcp" in message
    assert isinstance(raised.value, ToolAccessError)


async def test_a_name_three_servers_announce_names_all_three() -> None:
    """A message that stops at two sends the operator to unconfigure one server and meet this same refusal
    again — which is what the wording said until the third server existed."""
    definition = team(agent("reader", ["get_event"]))

    def one_tool(mcp) -> None:
        @mcp.tool(name="get_event", description="reads an event")
        def get_event() -> str:  # pragma: no cover - never called
            return "unused"

    async with (
        serving(build=one_tool) as market_url,
        serving(build=one_tool) as trading_url,
        serving(build=one_tool) as polymarket_url,
    ):
        registry = _registry(
            market_url, trading_mcp_url=trading_url, polymarket_mcp_url=polymarket_url
        )
        try:
            with pytest.raises(ToolNameCollision) as raised:
                await plan_tools(definition, registry)
        finally:
            await registry.aclose()

    message = str(raised.value)
    assert "'get_event'" in message
    assert "market-mcp" in message
    assert "trading-mcp" in message
    assert "polymarket-mcp" in message


async def test_tools_from_both_servers_resolve_to_the_server_that_announced_them() -> None:
    definition = team(agent("trader", ["read_indicators", "place_order"]))

    def write_tool(mcp) -> None:
        @mcp.tool(name="place_order", description="places an order")
        def place_order() -> str:  # pragma: no cover - never called
            return "unused"

    async with (
        serving(tools=("read_indicators",)) as market_url,
        serving(build=write_tool) as trading_url,
    ):
        registry = _registry(market_url, trading_mcp_url=trading_url)
        try:
            plan = await plan_tools(definition, registry)
            names = [tool.name for tool in plan.for_agent("trader")]
            assert names == ["read_indicators", "place_order"]

            # Dispatch reaches the right server: read_indicators only exists on
            # the market-mcp stand-in and place_order only on the trading-mcp one.
            from teams.tools import ToolOutcomeKind

            first = await plan.call(
                "read_indicators", {"symbol": "US100"}, agent_key="trader"
            )
            second = await plan.call("place_order", {}, agent_key="trader")
            assert first.kind is ToolOutcomeKind.OK
            assert second.kind is ToolOutcomeKind.OK
        finally:
            await registry.aclose()
