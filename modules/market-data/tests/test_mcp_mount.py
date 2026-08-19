"""The tool surface as a route of this application: where it is mounted, what it lists,
and the import order that keeps mounting it from breaking telemetry.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from starlette.routing import Mount
from test_tools_surface import EXPECTED_TOOL_NAMES

from market_data import app as app_module

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
