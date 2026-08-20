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
async def gateway(settings: Settings):
    """Closed in teardown rather than by each test's last line: an unclosed client is a
    warning, never a failure, so leaving it to the test is a rule nothing enforces."""
    client = GatewayClient(settings)
    yield client
    await client.aclose()


@pytest.fixture
def server(settings: Settings, gateway: GatewayClient):
    """The server, built on the base URL a test mocks. The client underneath it is the
    `gateway` fixture, so nothing here has to be closed by hand."""
    return build_server(settings, gateway)
