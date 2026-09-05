"""A tool surface mounted at `/mcp` serves across more than one lifespan of the same application."""

from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.routing import Mount

from tc_mcp_kit.mounted_server import (
    MOUNT_PATH,
    ToolSurfaceAddress,
    build_mcp_app,
    build_server,
    tool_surface_session,
)

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    },
}


def _register(mcp: FastMCP) -> None:
    @mcp.tool(name="say_hello", description="says hello")
    def say_hello() -> str:  # pragma: no cover - never called here
        return "hello"


def _app() -> Starlette:
    @asynccontextmanager
    async def lifespan(app: Starlette):
        async with tool_surface_session(app):
            yield

    server, tool_app = build_mcp_app(build_server("test", "test instructions", _register))
    app = Starlette(routes=[Mount(MOUNT_PATH, app=tool_app)], lifespan=lifespan)
    app.state.mcp_server = server
    app.add_middleware(ToolSurfaceAddress)
    return app


async def _initialize(app: Starlette) -> int:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://tests") as client:
            response = await client.post(
                MOUNT_PATH,
                json=INITIALIZE,
                headers={"Accept": "application/json, text/event-stream"},
            )
    return response.status_code


async def test_the_surface_serves_again_after_the_process_restarts() -> None:
    """The defect: a session manager runs once per instance, and the transport was bound to the first
    one at build time — so every lifespan after the first raised inside `run()` before a request arrived."""
    app = _app()

    assert await _initialize(app) == 200
    assert await _initialize(app) == 200
