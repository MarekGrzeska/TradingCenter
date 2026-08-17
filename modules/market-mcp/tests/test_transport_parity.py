"""Task 4.7: stdio and the network transport are two doors into the same server —
proven by walking through each one for real, not by asserting they share code.

Needs no running market-data — `list_tools()` never calls upstream — but does spawn
a real subprocess and bind a real port, so it is slower than the rest of this suite
(seconds, not milliseconds) without needing `--run-live` for it.
"""

from __future__ import annotations

import asyncio
import os
import socket
import sys
import threading
from pathlib import Path

import uvicorn
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client
from test_tool_surface import EXPECTED_TOOL_NAMES

from market_mcp.client import UpstreamClient
from market_mcp.config import Settings
from market_mcp.server import build_http_app

MODULE_ROOT = Path(__file__).resolve().parent.parent


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def _stdio_tool_names() -> set[str]:
    env = {**os.environ, "MARKET_DATA_URL": "http://127.0.0.1:8020"}
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "market_mcp", "stdio"],
        cwd=str(MODULE_ROOT),
        env=env,
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.list_tools()
        return {tool.name for tool in result.tools}


async def _http_tool_names(port: int) -> set[str]:
    settings = Settings(market_data_url="http://127.0.0.1:8020", mcp_http_port=port, _env_file=None)  # type: ignore[call-arg]
    upstream = UpstreamClient(settings)
    # The real shape `__main__.py` serves — wrapped with the caller-identity check,
    # not the bare `streamable_http_app()` — so this test proves what actually runs.
    app = build_http_app(settings, upstream)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            await asyncio.sleep(0.05)
        else:
            raise RuntimeError("streamable-http server did not start in time")

        async with (
            streamable_http_client(f"http://127.0.0.1:{port}/mcp") as (read, write, _get_id),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            result = await session.list_tools()
            return {tool.name for tool in result.tools}
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        await upstream.aclose()


async def test_stdio_and_streamable_http_publish_the_same_tools() -> None:
    stdio_names = await _stdio_tool_names()
    http_names = await _http_tool_names(_free_port())

    assert stdio_names == http_names
    # Against the one list that names them, rather than a number here: this test is about
    # the two doors agreeing, and a literal count made adding a tool fail in a file that
    # has nothing to say about the tool set.
    assert stdio_names == EXPECTED_TOOL_NAMES
