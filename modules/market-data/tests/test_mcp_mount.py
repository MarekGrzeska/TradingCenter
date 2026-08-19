"""The tool surface as a route of this application: where it is mounted, what it lists,
and the import order that keeps mounting it from breaking telemetry.

The handshake test at the bottom is the one that matters most, and it is here because it
was missing. Everything else in this file — and every tool test in the suite — reaches the
tools through objects: `FastMCP.call_tool`, or an in-memory session against the lowlevel
server. Not one of them crossed the mount, so three separate defects rode into production
on 19 August 2026 inside a change whose tests were green:

* the transport served itself at `/mcp` *inside* an app mounted at `/mcp`, so the address
  every caller was configured with was really `/mcp/mcp`;
* the mounted app's lifespan never ran, so the session manager's task group was never
  started and every request died on `RuntimeError: Task group is not initialized`;
* FastMCP turns DNS-rebinding protection on for a loopback `host`, which is its default,
  so every request carrying a real `Host` header was answered `421`.

One request through the front door would have caught all three.
"""

from __future__ import annotations

import ast
import contextlib
import inspect
import json
import types
from pathlib import Path

import httpx
import pytest
from starlette.routing import Mount
from test_tools_surface import EXPECTED_TOOL_NAMES

from market_data import app as app_module
from market_data.mcp_app import tool_surface_session

# Anything that pulls in FastAPI, Starlette or the MCP library. `telemetry.configure()`
# instruments libraries by patching them, so a module imported above that call is
# instrumented too late — silently, with the only symptom a span that never appears.
INSTRUMENTED = ("fastapi", "starlette", "mcp", "market_data.mcp_app")


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
    `FastMCP.list_tools()` — the same eleven names the separate process published, which
    is the whole promise of this move to its two callers.
    """
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


def test_nothing_instrumented_is_imported_above_telemetry_configure() -> None:
    """`telemetry.configure()` has to run before FastAPI, Starlette or the MCP library are
    imported, which is why `app.py`'s import block is split around it and why `mcp_app` is
    imported inside `create_app()`. Both are invisible conventions a tidying import sort
    would undo, so the order is asserted rather than commented."""
    source = Path(inspect.getfile(app_module)).read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Module level, and only there: the call this order is about is the one that runs at
    # import time, not a `configure` some function happens to call later.
    configure_at = next(
        node.lineno
        for node in tree.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and node.value.func.attr == "configure"
        and isinstance(node.value.func.value, ast.Name)
        and node.value.func.value.id == "telemetry"
    )

    for node in tree.body:  # module level only — an import inside a function cannot climb
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        for name in names:
            if any(name == root or name.startswith(f"{root}.") for root in INSTRUMENTED):
                assert node.lineno > configure_at, (
                    f"{name} is imported at line {node.lineno}, above telemetry.configure() "
                    f"at line {configure_at}"
                )


# --- the front door, end to end --------------------------------------------------------

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

# A real deployed host, not `testserver`: the DNS-rebinding check FastMCP enables by
# default rejects exactly this kind of Host header, and a test addressing localhost would
# not have noticed.
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
    """Both spellings of the address, because a mount answers the one with the trailing
    slash and a client posts the one without — and a POST does not follow the 307 between
    them (`mcp_app.ToolSurfaceAddress`)."""
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
