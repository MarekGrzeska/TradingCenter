"""A real MCP server to test the client against, not a mock of one.

`market-mcp` is not importable from here — no cross-module imports — so the stand-in is a
FastMCP server built in this file and served by a real uvicorn on a real port. That is
enough to prove what the client owes the run above it: a tool list it did not write, a
refusal that arrives as a result, and a server that is not there arriving as something
else again.

Slower than the rest of this suite (a second or two, binding a port), and worth it: the
one contract in this repository with no committed snapshot is this session, so a mocked
session would be a test of the mock. Duplicated from `agent/tests/test_tool_server.py`'s
own stand-in for the usual reason — no shared library, not even between test suites.
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager

import uvicorn
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

from teams.config import Settings

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
        database_url="postgresql://localhost:5432/teams",
        openai_api_key="key",
        models=ONE_MODEL,  # type: ignore[arg-type]
        market_mcp_url=url,
        _env_file=None,  # type: ignore[call-arg]
        **overrides,
    )


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _PairOut(BaseModel):
    symbol: str
    resolution: str


def _register(mcp: FastMCP, name: str) -> None:
    """The stand-in's catalogue, keyed by name so a test can serve a subset — which is
    how "the server stopped announcing a tool" is reproduced without a second file."""
    if name == "get_last_price":

        @mcp.tool(name=name, description="Returns the last price for a symbol, in UTC, bid side.")
        def get_last_price(symbol: str) -> str:
            if symbol != "US100":
                # The shape market-mcp refuses in: a sentence naming what to change.
                # Raising is how a FastMCP tool reports one, and it arrives as
                # isError=True.
                raise ValueError(f"nobody collects {symbol}. Call list_tracked_pairs first.")
            return "US100 last traded at 21000.5 at 2026-08-12T10:00:00Z, 3 minutes ago."

    elif name == "list_tracked_pairs":

        @mcp.tool(name=name, description="Lists the pairs the archive collects. At most 50.")
        def list_tracked_pairs() -> list[_PairOut]:
            # Typed list return on purpose: the SDK splits it into one content block per
            # item, which is the shape that broke `agent`'s client in production.
            return [
                _PairOut(symbol="US100", resolution="MINUTE_5"),
                _PairOut(symbol="US100", resolution="HOUR"),
            ]

    elif name == "read_indicators":

        @mcp.tool(name=name, description="Reads indicator values for a symbol.")
        def read_indicators(symbol: str) -> str:
            return f"{symbol}: RSI 61, ATR 42"

    else:  # pragma: no cover - a typo in a test, caught the moment it is written
        raise KeyError(f"the stand-in has no tool called {name!r}")


DEFAULT_TOOLS = ("get_last_price", "list_tracked_pairs", "read_indicators")


@contextmanager
def serving_sync(tools: tuple[str, ...] = DEFAULT_TOOLS) -> Iterator[str]:
    """The same stand-in for a test that is not itself async — `TestClient` drives the app
    through its own portal, so a test around it cannot be a coroutine."""
    port = free_port()
    mcp = FastMCP("stand-in", host="127.0.0.1", port=port)
    for name in tools:
        _register(mcp, name)

    config = uvicorn.Config(
        mcp.streamable_http_app(), host="127.0.0.1", port=port, log_level="error"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    else:  # pragma: no cover - only reached if the stand-in never comes up
        raise RuntimeError("the stand-in tool server did not start in time")

    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


@asynccontextmanager
async def serving(
    tools: tuple[str, ...] = DEFAULT_TOOLS,
    *,
    build: Callable[[FastMCP], None] | None = None,
) -> AsyncIterator[str]:
    """A stand-in server on a free port for the duration of the block. Yields its URL."""
    port = free_port()
    mcp = FastMCP("stand-in", host="127.0.0.1", port=port)
    if build is not None:
        build(mcp)
    else:
        for name in tools:
            _register(mcp, name)

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
    else:  # pragma: no cover - only reached if the stand-in never comes up
        raise RuntimeError("the stand-in tool server did not start in time")

    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
