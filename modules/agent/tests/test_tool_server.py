"""The client against a real MCP server, not a mock of one.

`market-mcp` is not importable from here — no cross-module imports — so the stand-in is
a two-tool FastMCP server built in this file and served by a real uvicorn on a real
port. That is enough to prove the three things this client owes the turn above it: a
tool list it did not write, a refusal that arrives as a result, and an unreachable
server that arrives as something else.

Slower than the rest of this suite (a second or two, binding a port), and worth it: the
one contract in this repository with no committed snapshot is this session, so a mocked
session would be a test of the mock.
"""

from __future__ import annotations

import asyncio
import socket
import threading
from collections.abc import AsyncIterator

import pytest
import uvicorn
from mcp.server.fastmcp import FastMCP

from agent.config import Settings
from agent.tools import ToolOutcomeKind, ToolServer

ONE_MODEL = [
    {
        "id": "gpt-5.6-luna",
        "model": "luna-prod",
        "display_name": "Luna",
        "cost_rank": 1,
        "input_rate_per_1m": "1",
        "output_rate_per_1m": "6",
    }
]


def settings_for(url: str | None, **overrides) -> Settings:
    return Settings(
        database_url="postgresql://localhost:5432/agent",
        openai_api_key="key",
        models=ONE_MODEL,
        default_model_id="gpt-5.6-luna",
        market_mcp_url=url,
        _env_file=None,  # type: ignore[call-arg]
        **overrides,
    )


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _stand_in_server(port: int) -> FastMCP:
    mcp = FastMCP("stand-in", host="127.0.0.1", port=port)

    @mcp.tool(description="Returns the last price for a symbol, in UTC, bid side.")
    def get_last_price(symbol: str) -> str:
        if symbol != "US100":
            # The shape market-mcp refuses in: a sentence naming what to change. Raising
            # is how a FastMCP tool reports one, and it arrives as isError=True.
            raise ValueError(f"nobody collects {symbol}. Call list_tracked_pairs first.")
        return "US100 last traded at 21000.5 at 2026-08-12T10:00:00Z, 3 minutes ago."

    @mcp.tool(description="Lists the pairs the archive collects. At most 50.")
    def list_tracked_pairs() -> str:
        return "US100, EURUSD"

    return mcp


@pytest.fixture
async def tool_server() -> AsyncIterator[ToolServer]:
    port = _free_port()
    app = _stand_in_server(port).streamable_http_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        await asyncio.sleep(0.05)
    else:  # pragma: no cover - only reached if the stand-in never comes up
        raise RuntimeError("the stand-in tool server did not start in time")

    client = ToolServer(settings_for(f"http://127.0.0.1:{port}"))
    try:
        yield client
    finally:
        await client.aclose()
        server.should_exit = True
        thread.join(timeout=5)


async def test_the_tool_list_comes_from_the_server(tool_server: ToolServer) -> None:
    tools = await tool_server.list_tools()

    assert {tool.name for tool in tools} == {"get_last_price", "list_tracked_pairs"}
    # The description is the server's, not a copy kept here — this is the assertion that
    # would fail the day someone writes a local catalogue (specs/agent-tool-access).
    price = next(tool for tool in tools if tool.name == "get_last_price")
    assert "bid side" in price.description
    assert price.input_schema["properties"]["symbol"]["type"] == "string"


async def test_the_tool_list_is_read_once_per_session(tool_server: ToolServer) -> None:
    first = await tool_server.list_tools()
    second = await tool_server.list_tools()

    assert first is second


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
    # The point of the whole shape: the model can act on this sentence.
    assert "list_tracked_pairs" in outcome.text


async def test_an_unknown_tool_is_a_refusal_not_an_outage(tool_server: ToolServer) -> None:
    outcome = await tool_server.call("delete_everything", {})

    assert outcome.kind is ToolOutcomeKind.REFUSED


async def test_an_unreachable_server_is_unavailable_not_a_refusal() -> None:
    # A port nothing is listening on: the call was never made, which is a different
    # fact from the archive having no data (specs/agent-tool-access).
    client = ToolServer(settings_for(f"http://127.0.0.1:{_free_port()}"))
    try:
        outcome = await client.call("get_last_price", {"symbol": "US100"})
    finally:
        await client.aclose()

    assert outcome.kind is ToolOutcomeKind.UNAVAILABLE
    assert "says nothing about the archive" in outcome.text


async def test_an_unreachable_server_publishes_no_tools_rather_than_failing() -> None:
    client = ToolServer(settings_for(f"http://127.0.0.1:{_free_port()}"))
    try:
        assert await client.list_tools() == []
    finally:
        await client.aclose()


async def test_a_slow_server_times_out_as_unavailable() -> None:
    port = _free_port()
    mcp = FastMCP("slow", host="127.0.0.1", port=port)

    @mcp.tool(description="Never answers in time. At most 1 call.")
    async def sleeps() -> str:
        await asyncio.sleep(30)
        return "never"

    config = uvicorn.Config(
        mcp.streamable_http_app(), host="127.0.0.1", port=port, log_level="error"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        await asyncio.sleep(0.05)

    client = ToolServer(
        settings_for(f"http://127.0.0.1:{port}", market_mcp_request_timeout_seconds=1.0)
    )
    try:
        outcome = await client.call("sleeps", {})
    finally:
        await client.aclose()
        server.should_exit = True
        thread.join(timeout=5)

    assert outcome.kind is ToolOutcomeKind.UNAVAILABLE
    assert "did not answer within" in outcome.text


async def test_no_configured_server_means_no_tools_and_no_calls() -> None:
    client = ToolServer(settings_for(None))
    try:
        assert client.configured is False
        assert await client.list_tools() == []
        outcome = await client.call("get_last_price", {"symbol": "US100"})
    finally:
        await client.aclose()

    assert outcome.kind is ToolOutcomeKind.UNAVAILABLE
    assert "no tool server is configured" in outcome.text
