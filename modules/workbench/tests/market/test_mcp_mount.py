"""The tool surface as a route of this application: where it is mounted and what it lists. One request through
the front door caught three defects; the import order that keeps telemetry whole is the host's test now."""

from __future__ import annotations

import contextlib
import json
import types

import httpx
import pytest
from starlette.routing import Mount

from market_data import app as app_module
from market_data.mcp_app import tool_surface_session

from .test_tools_surface import EXPECTED_TOOL_NAMES


def test_the_tool_surface_is_mounted_at_slash_mcp() -> None:
    app = app_module.create_app()
    mounts = {route.path: route for route in app.routes if isinstance(route, Mount)}
    assert "/mcp" in mounts


def test_the_mount_does_not_shadow_a_rest_route() -> None:
    """A mount swallows everything below its path. `/mcp` is not a prefix of any route
    this module publishes, and this is what says so out loud."""
    app = app_module.create_app()
    published = [getattr(route, "path", "") for route in app.routes]
    assert not [path for path in published if path.startswith("/mcp/")]


async def test_a_session_lists_exactly_the_expected_tools() -> None:
    """The list a client actually receives, through a real MCP session rather than through
    `FastMCP.list_tools()` — the same eleven names the separate process published."""
    from mcp.shared.memory import create_connected_server_and_client_session

    from market_data.mcp_app import build_server

    class _State:
        pass

    class _App:
        state = _State()

    server = build_server(_App())
    async with create_connected_server_and_client_session(server._mcp_server) as client:
        listed = await client.list_tools()

    assert {tool.name for tool in listed.tools} == EXPECTED_TOOL_NAMES


INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "the test", "version": "1"},
    },
}

# A real deployed host, not `testserver`: the DNS-rebinding check FastMCP enables by default rejects
# exactly this kind of Host header, and a test addressing localhost would not have noticed.
BASE = "https://app-tradingcenter-market-data.azurewebsites.net"

MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


def _result(body: str) -> dict:
    """The JSON out of a server-sent-events reply, which is how this transport answers."""
    for line in body.splitlines():
        if line.startswith("data: "):
            return json.loads(line[len("data: ") :])
    raise AssertionError(f"no SSE data frame in: {body[:200]}")


@pytest.mark.parametrize("path", ["/mcp", "/mcp/"])
async def test_a_session_initializes_through_the_mounted_path(app, settings, path: str) -> None:
    """Both spellings of the address, because a mount answers the one with the trailing slash and a
    client posts the one without — and a POST does not follow the 307 between them."""
    app.state.settings = settings

    async with tool_surface_session(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url=BASE) as client:
            response = await client.post(path, headers=MCP_HEADERS, json=INITIALIZE)

    assert response.status_code == 200, response.text
    assert response.headers.get("mcp-session-id")
    assert _result(response.text)["result"]["serverInfo"]["name"] == "market-data"


async def test_the_whole_tool_list_comes_back_over_the_transport(app, settings) -> None:
    """The list `agent` and `teams` read at the start of a session, fetched the way they
    fetch it: over HTTP, through the mount, in a session with an id."""
    app.state.settings = settings

    async with tool_surface_session(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url=BASE) as client:
            opened = await client.post("/mcp", headers=MCP_HEADERS, json=INITIALIZE)
            session = {"mcp-session-id": opened.headers["mcp-session-id"]}
            await client.post(
                "/mcp",
                headers={**MCP_HEADERS, **session},
                json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            )
            listed = await client.post(
                "/mcp",
                headers={**MCP_HEADERS, **session},
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            )

    assert listed.status_code == 200, listed.text
    names = {tool["name"] for tool in _result(listed.text)["result"]["tools"]}
    assert names == EXPECTED_TOOL_NAMES


def test_nothing_mounted_means_nothing_to_start() -> None:
    """The suites that drive the lifespan build their own applications; one without a tool
    surface has no session manager and must not be an error."""
    bare = types.SimpleNamespace(state=types.SimpleNamespace())

    assert isinstance(tool_surface_session(bare), contextlib.AbstractAsyncContextManager)
