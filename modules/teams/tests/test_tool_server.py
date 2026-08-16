"""The session with a real MCP server: what it publishes, and the three outcomes a call
can have. The stand-in and its helpers live in `mcp_stand_in.py`."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import pytest
from mcp.server.fastmcp import FastMCP

from teams.tools import ToolOutcomeKind, ToolServer, ToolServerUnavailable

from .mcp_stand_in import free_port, serving, settings_for


@pytest.fixture
async def tool_server() -> AsyncIterator[ToolServer]:
    async with serving() as url:
        client = ToolServer(settings_for(url))
        try:
            yield client
        finally:
            await client.aclose()


async def test_the_tool_list_comes_from_the_server(tool_server: ToolServer) -> None:
    tools = await tool_server.list_tools()

    assert {tool.name for tool in tools} == {
        "get_last_price",
        "list_tracked_pairs",
        "read_indicators",
    }
    # The description is the server's, not a copy kept here — this is the assertion that
    # would fail the day someone writes a local catalogue (specs/teams-tool-access, "Moduł
    # nie trzyma kopii tego, co ogłasza serwer narzędzi").
    price = next(tool for tool in tools if tool.name == "get_last_price")
    assert "bid side" in price.description
    assert price.input_schema["properties"]["symbol"]["type"] == "string"


async def test_the_tool_list_is_read_once_per_session(tool_server: ToolServer) -> None:
    first = await tool_server.list_tools()
    second = await tool_server.list_tools()

    assert first is second


async def test_a_reworded_tool_needs_no_revision_rewritten() -> None:
    """specs/teams-tool-access, "Opis narzędzia zmienia się po stronie serwera": the
    definition names tools and nothing else, so a new description arrives simply by being
    read from the session that will use it."""

    def one_tool(wording: str):
        def build(mcp: FastMCP) -> None:
            @mcp.tool(name="get_last_price", description=wording)
            def get_last_price(symbol: str) -> str:  # pragma: no cover - never called here
                return "unused"

        return build

    async with serving(build=one_tool("The old wording.")) as url:
        before = ToolServer(settings_for(url))
        try:
            first = await before.list_tools()
        finally:
            await before.aclose()

    async with serving(build=one_tool("The new wording, decided on the server.")) as url:
        after = ToolServer(settings_for(url))
        try:
            second = await after.list_tools()
        finally:
            await after.aclose()

    assert first[0].description == "The old wording."
    assert second[0].description == "The new wording, decided on the server."


async def test_a_successful_call_carries_the_servers_text(tool_server: ToolServer) -> None:
    outcome = await tool_server.call("get_last_price", {"symbol": "US100"})

    assert outcome.kind is ToolOutcomeKind.OK
    assert "21000.5" in outcome.text
    assert outcome.duration_ms >= 0


async def test_a_refusal_arrives_as_a_result_with_the_servers_own_words(
    tool_server: ToolServer,
) -> None:
    outcome = await tool_server.call("get_last_price", {"symbol": "NOPE"})

    assert outcome.kind is ToolOutcomeKind.REFUSED
    # The point of the whole shape: the agent can act on this sentence.
    assert "list_tracked_pairs" in outcome.text


async def test_a_bare_list_return_reads_back_as_one_json_array(tool_server: ToolServer) -> None:
    """The production bug `agent` hit: the SDK splits a typed-list return into one content
    block per item, and joining them is N JSON documents rather than one. Reading
    `structuredContent` is what answers it."""
    outcome = await tool_server.call("list_tracked_pairs", {})

    assert outcome.kind is ToolOutcomeKind.OK
    assert json.loads(outcome.text) == {
        "result": [
            {"symbol": "US100", "resolution": "MINUTE_5"},
            {"symbol": "US100", "resolution": "HOUR"},
        ]
    }


async def test_an_unknown_tool_is_a_refusal_not_an_outage(tool_server: ToolServer) -> None:
    outcome = await tool_server.call("delete_everything", {})

    assert outcome.kind is ToolOutcomeKind.REFUSED


async def test_an_unreachable_server_cannot_publish_a_tool_list() -> None:
    """The divergence from `agent`'s twin, asserted: there, this answers `[]` and the turn
    goes on without tools. Here it raises, because a team that was assigned tools must be
    refused rather than left guessing (specs/teams-tool-access)."""
    client = ToolServer(settings_for(f"http://127.0.0.1:{free_port()}"))
    try:
        with pytest.raises(ToolServerUnavailable) as raised:
            await client.list_tools()
    finally:
        await client.aclose()

    message = str(raised.value)
    # Both halves of the transport run in an anyio task group, so the raw exception is
    # "unhandled errors in a TaskGroup (1 sub-exception)" — a sentence naming nothing.
    assert "TaskGroup" not in message
    assert "could not be reached" in message


async def test_an_unreachable_server_makes_a_call_unavailable_not_a_refusal() -> None:
    # A call is a different matter from the list: mid-run, an unreachable server costs one
    # agent one answer, and the run keeps its trace.
    client = ToolServer(settings_for(f"http://127.0.0.1:{free_port()}"))
    try:
        outcome = await client.call("get_last_price", {"symbol": "US100"})
    finally:
        await client.aclose()

    assert outcome.kind is ToolOutcomeKind.UNAVAILABLE
    assert "says nothing about what the tool would have answered" in outcome.text
    assert "TaskGroup" not in outcome.text


async def test_a_slow_server_times_out_as_unavailable_not_as_a_refusal() -> None:
    """specs/teams-tool-access, "Wołanie serwera narzędzi ma skończony czas": the two
    facts are different, and the trace has to be able to tell them apart."""

    def build(mcp: FastMCP) -> None:
        @mcp.tool(name="sleeps", description="Never answers in time.")
        async def sleeps() -> str:
            await asyncio.sleep(30)
            return "never"  # pragma: no cover - the call never gets this far

    async with serving(build=build) as url:
        client = ToolServer(settings_for(url, market_mcp_request_timeout_seconds=1.0))
        try:
            outcome = await client.call("sleeps", {})
        finally:
            await client.aclose()

    assert outcome.kind is ToolOutcomeKind.UNAVAILABLE
    assert "did not answer within" in outcome.text


async def test_no_configured_server_means_no_list_and_no_calls() -> None:
    client = ToolServer(settings_for(None))
    try:
        assert client.configured is False
        with pytest.raises(ToolServerUnavailable) as raised:
            await client.list_tools()
        outcome = await client.call("get_last_price", {"symbol": "US100"})
    finally:
        await client.aclose()

    assert "MARKET_MCP_URL is unset" in str(raised.value)
    assert outcome.kind is ToolOutcomeKind.UNAVAILABLE
    assert "no tool server is configured" in outcome.text


def test_describe_unwraps_nested_task_groups() -> None:
    from teams.tools.client import _describe

    refused = ConnectionRefusedError("All connection attempts failed")
    nested = BaseExceptionGroup("outer", [BaseExceptionGroup("inner", [refused, refused])])

    described = _describe(nested)

    assert described == "All connection attempts failed"
    assert "TaskGroup" not in described
    assert "ExceptionGroup" not in described


async def test_one_session_serves_agents_that_are_separate_tasks(tool_server: ToolServer) -> None:
    """A run works several agents at once (specs/teams-runs), so the session is opened in
    one task and used from others.

    Worth an explicit test rather than an assumption: the transport runs its halves in an
    anyio task group, and a task group whose scope is exited by a different task than
    entered it is a documented way to get `RuntimeError`. It holds — this is the test that
    says so, and the one that would fail if a future SDK stopped tolerating it.
    """
    concurrent = await asyncio.gather(
        asyncio.create_task(tool_server.call("get_last_price", {"symbol": "US100"})),
        asyncio.create_task(tool_server.call("read_indicators", {"symbol": "US100"})),
        asyncio.create_task(tool_server.call("list_tracked_pairs", {})),
    )

    assert [outcome.kind for outcome in concurrent] == [ToolOutcomeKind.OK] * 3
    # Closing from a further task is the lifespan's shutdown path.
    await asyncio.create_task(tool_server.aclose())
