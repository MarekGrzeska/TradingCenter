"""A real MCP server to test the clients against, not a mock of one. The stand-in is a FastMCP server built
in this file and served by a real uvicorn on a real port — enough to prove what a client owes the run above
it: a tool list it did not write, a refusal that arrives as a result, and a server that is not there.

One copy at the root of `tests/`, because there is one process now. What is still per-suite is
`settings_for`, since each surface builds its own `Settings`."""

from __future__ import annotations

import asyncio
import socket
import threading
import time
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel

# What market-mcp puts on every one of its tools. The stand-in carries it for the same reason it is a real
# server rather than a mock: a check that reads annotations would otherwise be tested against nothing real.
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)

STARTUP_ATTEMPTS = 100
STARTUP_POLL_SECONDS = 0.05


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
        # Deliberately unannotated, and the only one here that is: `read_only=None` is a third answer
        # market-mcp could give, and a test pins that it travels as "unknown" rather than as a guess.
        @mcp.tool(name=name, description="Returns the last price for a symbol, in UTC, bid side.")
        def get_last_price(symbol: str) -> str:
            if symbol != "US100":
                # The shape market-mcp refuses in: a sentence naming what to change. Raising is how a
                # FastMCP tool reports one, and it arrives as isError=True.
                raise ValueError(f"nobody collects {symbol}. Call list_tracked_pairs first.")
            return "US100 last traded at 21000.5 at 2026-08-12T10:00:00Z, 3 minutes ago."

    elif name == "list_tracked_pairs":

        @mcp.tool(
            name=name,
            description="Lists the pairs the archive collects. At most 50.",
            annotations=READ_ONLY,
        )
        def list_tracked_pairs() -> list[_PairOut]:
            # Typed list return on purpose: the SDK splits it into one content block per
            # item, which is the shape that broke `agent`'s client in production.
            return [
                _PairOut(symbol="US100", resolution="MINUTE_5"),
                _PairOut(symbol="US100", resolution="HOUR"),
            ]

    elif name == "read_indicators":

        @mcp.tool(
            name=name,
            description="Reads indicator values for a symbol.",
            annotations=READ_ONLY,
        )
        def read_indicators(symbol: str) -> str:
            return f"{symbol}: RSI 61, ATR 42"

    elif name == "place_order":
        # A trading-mcp-shaped tool for tests standing in for the write server — the
        # one thing about it that matters here is the annotation, not the behaviour.
        @mcp.tool(
            name=name,
            description="Places an order.",
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
        )
        def place_order() -> str:
            return "order placed"

    else:  # pragma: no cover - a typo in a test, caught the moment it is written
        raise KeyError(f"the stand-in has no tool called {name!r}")


DEFAULT_TOOLS = ("get_last_price", "list_tracked_pairs", "read_indicators")


def _start(app, port: int) -> tuple[uvicorn.Server, threading.Thread]:
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    return server, thread


def _stop(server: uvicorn.Server, thread: threading.Thread) -> None:
    server.should_exit = True
    thread.join(timeout=5)


def _build(tools: tuple[str, ...], port: int, build: Callable[[FastMCP], None] | None) -> FastMCP:
    mcp = FastMCP("stand-in", host="127.0.0.1", port=port)
    if build is not None:
        build(mcp)
    else:
        for name in tools:
            _register(mcp, name)
    return mcp


@contextmanager
def serving_sync(tools: tuple[str, ...] = DEFAULT_TOOLS) -> Iterator[str]:
    """The same stand-in for a test that is not itself async — `TestClient` drives the app
    through its own portal, so a test around it cannot be a coroutine."""
    port = free_port()
    server, thread = _start(_build(tools, port, None).streamable_http_app(), port)
    for _ in range(STARTUP_ATTEMPTS):
        if server.started:
            break
        time.sleep(STARTUP_POLL_SECONDS)
    else:  # pragma: no cover - only reached if the stand-in never comes up
        raise RuntimeError("the stand-in tool server did not start in time")

    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        _stop(server, thread)


@asynccontextmanager
async def serving_app(app, port: int) -> AsyncIterator[None]:
    """One ASGI application on a port of the caller's choosing, for callers that build their own stand-in —
    so the same port can be served twice, which is what a redeploy looks like from the client's side."""
    server, thread = _start(app, port)
    for _ in range(STARTUP_ATTEMPTS):
        if server.started:
            break
        await asyncio.sleep(STARTUP_POLL_SECONDS)
    else:  # pragma: no cover - only reached if the stand-in never comes up
        raise RuntimeError("the stand-in tool server did not start in time")
    try:
        yield
    finally:
        _stop(server, thread)


@asynccontextmanager
async def serving(
    tools: tuple[str, ...] = DEFAULT_TOOLS,
    *,
    build: Callable[[FastMCP], None] | None = None,
    port: int | None = None,
) -> AsyncIterator[str]:
    """A stand-in server on a free port for the duration of the block. `port` pins it, which is how a
    restart is reproduced: the same URL served by a second server that never heard of the first."""
    port = free_port() if port is None else port
    async with serving_app(_build(tools, port, build).streamable_http_app(), port):
        yield f"http://127.0.0.1:{port}"
