from __future__ import annotations

from typing import Any

import jsonschema
import pytest
from mcp.server.fastmcp import FastMCP

from market_mcp.client import UpstreamClient
from market_mcp.config import Settings
from market_mcp.server import build_server

BASE = "http://127.0.0.1:8020"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="run tests that need a real running market-data instance",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-live"):
        return
    skip = pytest.mark.skip(reason="needs --run-live and a running market-data instance")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _no_ambient_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep a developer's real .env out of the tests — `Settings` reads the environment
    and the .env file, so without this a machine holding one runs different tests than
    a machine without it."""
    for name in (
        "MARKET_DATA_URL",
        "MARKET_DATA_SCOPE",
        "MCP_HTTP_PORT",
        "MCP_REQUEST_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def settings() -> Settings:
    return Settings(market_data_url=BASE, _env_file=None)  # type: ignore[call-arg]


@pytest.fixture
def server(settings: Settings):
    """The server and the client it was built with, so a test can close the client
    and mock the exact base URL it will call."""
    upstream = UpstreamClient(settings)
    mcp = build_server(settings, upstream)
    _check_output_schema(mcp)
    return mcp, upstream


def _check_output_schema(mcp: FastMCP) -> None:
    """Put back the check the tests would otherwise skip.

    Over the wire the lowlevel server validates every structured reply against the tool's
    published `outputSchema` and turns a mismatch into a refusal the caller sees instead
    of the answer. `FastMCP.call_tool` — the entry point every test here uses — does not,
    so a tool can be green in CI and refuse itself on every real call. That is not
    hypothetical: `serialization_alias` on the output models published `from_` in the
    schema and wrote `from` in the reply, and all four window-carrying tools answered
    `Output validation error: 'from_' is a required property` (see `WindowedOut`).
    """
    original = mcp.call_tool
    schemas: dict[str, dict[str, Any] | None] = {}

    async def checked(name: str, arguments: dict[str, Any], **kwargs: Any):
        content, structured = await original(name, arguments, **kwargs)
        if not schemas:
            schemas.update({tool.name: tool.outputSchema for tool in await mcp.list_tools()})
        schema = schemas.get(name)
        if schema is not None and structured is not None:
            jsonschema.validate(instance=structured, schema=schema)
        return content, structured

    mcp.call_tool = checked  # type: ignore[method-assign]
