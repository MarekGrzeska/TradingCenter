from __future__ import annotations

import pytest

from trading_mcp.client import GatewayClient
from trading_mcp.config import Settings
from trading_mcp.server import build_server

BASE = "http://127.0.0.1:8010"
KEY = "test-gateway-key"


@pytest.fixture(autouse=True)
def _no_ambient_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep a developer's real .env out of the tests — `Settings` reads the environment
    and the .env file, so without this a machine holding one runs different tests than
    a machine without it."""
    for name in (
        "CAPITAL_GATEWAY_URL",
        "CAPITAL_GATEWAY_API_KEY",
        "CAPITAL_GATEWAY_REQUEST_TIMEOUT_SECONDS",
        "TRADING_MCP_PORT",
        "TRADING_MCP_HOST",
        "REQUIRE_AUTHENTICATED_PRINCIPAL",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        capital_gateway_url=BASE,
        capital_gateway_api_key=KEY,
        _env_file=None,  # type: ignore[call-arg]
    )


@pytest.fixture
def gateway(settings: Settings) -> GatewayClient:
    return GatewayClient(settings)


@pytest.fixture
def server(settings: Settings, gateway: GatewayClient):
    """The server and the gateway client it was built with, so a test can close the
    client and mock the exact base URL it will call — same shape as market-mcp's own
    `server` fixture."""
    mcp = build_server(settings, gateway)
    return mcp, gateway
