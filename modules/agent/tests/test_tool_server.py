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
import json
import socket
import threading
from collections.abc import AsyncIterator

import pytest
import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel

from agent.config import Settings
from agent.tools import ToolDescriptor, ToolOutcomeKind, ToolServer

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


class _PairOut(BaseModel):
    symbol: str
    resolution: str


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

    # market-mcp's real `list_tracked_pairs` returns `list[TrackedPairOut]`, not a
    # string — the shape this stand-in exists to reproduce. The SDK turns a bare list
    # return into one content block *per item* rather than one for the whole array
    # (`_convert_to_content`), so a client reading `content` alone sees N JSON documents
    # back to back, not the one array `structuredContent` carries.
    @mcp.tool(description="Lists pairs the typed way — the shape that broke the client.")
    def list_pairs_typed() -> list[_PairOut]:
        return [_PairOut(symbol="US100", resolution="MINUTE_5"), _PairOut(symbol="US100", resolution="HOUR")]

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

    assert {tool.name for tool in tools} == {
        "get_last_price",
        "list_tracked_pairs",
        "list_pairs_typed",
    }
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


async def test_a_bare_list_return_reads_back_as_one_json_array(tool_server: ToolServer) -> None:
    """The production bug: `list_tracked_pairs` answered "something unreadable" the
    moment more than one pair was tracked, because the SDK splits a bare-list return
    into one content block per item and joining them is N JSON documents, not one.
    Reading `structuredContent` instead is what `chart.py`'s `_check_pair` was already
    written to expect (`pairs.get("result", pairs.get("pairs", []))`)."""
    outcome = await tool_server.call("list_pairs_typed", {})

    assert outcome.kind is ToolOutcomeKind.OK
    parsed = json.loads(outcome.text)
    assert parsed == {
        "result": [
            {"symbol": "US100", "resolution": "MINUTE_5"},
            {"symbol": "US100", "resolution": "HOUR"},
        ]
    }


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
    # Both halves of the transport run in an anyio task group, so the raw exception is
    # "unhandled errors in a TaskGroup (1 sub-exception)" — a sentence naming nothing,
    # which a live run handed to the model before `_describe` existed.
    assert "TaskGroup" not in outcome.text
    assert "connection" in outcome.text.lower()


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
    # The message names which server, because there is more than one now and "the tool
    # server" stopped being unambiguous.
    assert "market-mcp" in outcome.text
    assert "not configured" in outcome.text


# --- a server whose writes land on the account (specs/agent-trading) ---


def _trading_stand_in(port: int) -> FastMCP:
    """trading-mcp's own annotations, on trading-mcp's own three shapes: a read, a write,
    and one carrying no annotation at all — the case that must not be read as a read."""
    mcp = FastMCP("trading-stand-in", host="127.0.0.1", port=port)

    @mcp.tool(
        description="Open positions.",
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True),
    )
    def get_positions() -> str:
        return "none"

    @mcp.tool(
        description="Sends an order.",
        annotations=ToolAnnotations(
            readOnlyHint=False, destructiveHint=True, idempotentHint=False
        ),
    )
    def place_order(symbol: str) -> str:
        return f"sent for {symbol}"

    @mcp.tool(description="Nobody annotated this one.")
    def unannotated() -> str:
        return "ok"

    return mcp


def _serve(app, port: int) -> tuple[uvicorn.Server, threading.Thread]:
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    return server, thread


@pytest.fixture
async def trading_server() -> AsyncIterator[ToolServer]:
    port = _free_port()
    server, thread = _serve(_trading_stand_in(port).streamable_http_app(), port)
    for _ in range(100):
        if server.started:
            break
        await asyncio.sleep(0.05)
    else:  # pragma: no cover - only reached if the stand-in never comes up
        raise RuntimeError("the trading stand-in did not start in time")

    client = ToolServer(
        settings_for(None, trading_mcp_url=f"http://127.0.0.1:{port}"),
        prefix="trading_mcp",
        can_move_the_account=True,
    )
    try:
        yield client
    finally:
        await client.aclose()
        server.should_exit = True
        thread.join(timeout=5)


async def test_the_read_only_hint_comes_from_the_server(trading_server: ToolServer) -> None:
    hints = {tool.name: tool.read_only for tool in await trading_server.list_tools()}

    assert hints == {"get_positions": True, "place_order": False, "unannotated": None}


async def test_an_unannotated_tool_counts_as_moving_the_account(
    trading_server: ToolServer,
) -> None:
    """`None` is "nobody said", not "it reads". Counting it as a write writes one row too
    many; counting it as a read loses the only record of an order."""
    await trading_server.list_tools()

    assert trading_server.moves_the_account("unannotated") is True
    assert trading_server.moves_the_account("place_order") is True
    assert trading_server.moves_the_account("get_positions") is False


async def test_a_name_this_server_never_described_counts_as_moving_the_account(
    trading_server: ToolServer,
) -> None:
    # The list is dropped whenever a session breaks, so "we cannot tell" resolves the
    # cautious way.
    assert trading_server.moves_the_account("place_order") is True


async def test_an_unreachable_write_is_unknown_rather_than_unavailable() -> None:
    """The difference the fourth outcome exists for: an order that never answered is
    either no position or one nobody knows about, and "the call was not made" is a claim
    this module cannot make about it (specs/agent-trading)."""
    client = ToolServer(
        settings_for(None, trading_mcp_url=f"http://127.0.0.1:{_free_port()}"),
        prefix="trading_mcp",
        can_move_the_account=True,
    )
    try:
        outcome = await client.call("place_order", {"symbol": "US100"})
    finally:
        await client.aclose()

    assert outcome.kind is ToolOutcomeKind.UNKNOWN
    assert "may have gone through" in outcome.text
    assert "do not send it again" in outcome.text
    assert "was not made" not in outcome.text


async def test_a_read_on_the_same_server_is_still_unavailable() -> None:
    """Reading positions is a read even on the server that can write: it changes nothing,
    so a failed one carries the same "nothing happened" market-mcp's does."""
    client = ToolServer(
        settings_for(None, trading_mcp_url=f"http://127.0.0.1:{_free_port()}"),
        prefix="trading_mcp",
        can_move_the_account=True,
    )
    # Seeded rather than read from a live server, because this client's port is dead on
    # purpose — the descriptor is what decides, and here it says "reads".
    client._tools = [
        ToolDescriptor(name="get_positions", description="", input_schema={}, read_only=True)
    ]
    try:
        outcome = await client.call("get_positions", {})
    finally:
        await client.aclose()

    assert outcome.kind is ToolOutcomeKind.UNAVAILABLE
    assert "says nothing about the archive" in outcome.text


async def test_a_server_that_cannot_move_the_account_never_answers_unknown() -> None:
    """market-mcp's own client, unchanged: every failure there is still `unavailable`,
    whatever a tool's annotation says."""
    client = ToolServer(settings_for(f"http://127.0.0.1:{_free_port()}"))
    try:
        assert client.moves_the_account("place_order") is False
        outcome = await client.call("place_order", {})
    finally:
        await client.aclose()

    assert outcome.kind is ToolOutcomeKind.UNAVAILABLE


async def test_a_slow_write_times_out_as_unknown() -> None:
    port = _free_port()
    mcp = FastMCP("slow-trading", host="127.0.0.1", port=port)

    @mcp.tool(
        description="Sends an order and never says whether it landed.",
        annotations=ToolAnnotations(readOnlyHint=False),
    )
    async def place_order(symbol: str) -> str:
        await asyncio.sleep(30)
        return "never"

    server, thread = _serve(mcp.streamable_http_app(), port)
    for _ in range(100):
        if server.started:
            break
        await asyncio.sleep(0.05)

    client = ToolServer(
        settings_for(
            None,
            trading_mcp_url=f"http://127.0.0.1:{port}",
            trading_mcp_request_timeout_seconds=1.0,
        ),
        prefix="trading_mcp",
        can_move_the_account=True,
    )
    try:
        await client.list_tools()
        outcome = await client.call("place_order", {"symbol": "US100"})
    finally:
        await client.aclose()
        server.should_exit = True
        thread.join(timeout=5)

    assert outcome.kind is ToolOutcomeKind.UNKNOWN
    assert "did not answer within" in outcome.text
    assert "may have gone through" in outcome.text


def test_describe_unwraps_nested_task_groups() -> None:
    from agent.tools.client import _describe

    refused = ConnectionRefusedError("All connection attempts failed")
    nested = BaseExceptionGroup("outer", [BaseExceptionGroup("inner", [refused, refused])])

    described = _describe(nested)

    assert described == "All connection attempts failed"
    assert "TaskGroup" not in described
    assert "ExceptionGroup" not in described


async def test_one_session_serves_turns_that_are_separate_tasks(tool_server: ToolServer) -> None:
    """The router runs every turn as its own `asyncio.create_task`, so the session is
    opened inside one task and then used and closed from others.

    Worth an explicit test rather than an assumption: the transport runs its halves in
    an anyio task group, and a task group whose scope is exited by a different task than
    entered it is a documented way to get `RuntimeError`. It holds here — this is the
    test that says so, and the one that would fail if a future SDK version stopped
    tolerating it.
    """
    first = await asyncio.create_task(tool_server.call("get_last_price", {"symbol": "US100"}))
    second = await asyncio.create_task(tool_server.call("list_tracked_pairs", {}))

    concurrent = await asyncio.gather(
        asyncio.create_task(tool_server.call("list_tracked_pairs", {})),
        asyncio.create_task(tool_server.call("get_last_price", {"symbol": "US100"})),
    )

    assert first.ok and second.ok
    assert [outcome.kind for outcome in concurrent] == [ToolOutcomeKind.OK, ToolOutcomeKind.OK]
    # Closing from a third task is the lifespan's shutdown path.
    await asyncio.create_task(tool_server.aclose())
