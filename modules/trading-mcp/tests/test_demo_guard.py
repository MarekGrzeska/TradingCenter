"""`ensure_demo_environment()`: refuse anything but the demo account, and re-check
after a failure rather than trust a stale answer (specs/trading-mcp-upstream-access)."""

from __future__ import annotations

import httpx
import pytest
import respx

from trading_mcp.client import GatewayClient
from trading_mcp.config import Settings
from trading_mcp.errors import GatewayUnavailable, NotDemoEnvironment

BASE = "http://127.0.0.1:8010"


@pytest.fixture
def client(settings: Settings) -> GatewayClient:
    return GatewayClient(settings)


@respx.mock
async def test_demo_environment_is_accepted(client: GatewayClient) -> None:
    respx.get(f"{BASE}/capabilities").mock(
        return_value=httpx.Response(200, json={"environment": "demo"})
    )

    await client.ensure_demo_environment()
    await client.aclose()


@respx.mock
async def test_non_demo_environment_is_refused(client: GatewayClient) -> None:
    respx.get(f"{BASE}/capabilities").mock(
        return_value=httpx.Response(200, json={"environment": "live"})
    )

    with pytest.raises(NotDemoEnvironment, match="live"):
        await client.ensure_demo_environment()
    await client.aclose()


@respx.mock
async def test_result_is_cached_and_the_gateway_is_asked_once(client: GatewayClient) -> None:
    route = respx.get(f"{BASE}/capabilities").mock(
        return_value=httpx.Response(200, json={"environment": "demo"})
    )

    await client.ensure_demo_environment()
    await client.ensure_demo_environment()

    assert route.call_count == 1
    await client.aclose()


@respx.mock
async def test_a_failed_call_forces_a_fresh_check_next_time(client: GatewayClient) -> None:
    """A read that fails after the environment was verified means the connection
    dropped and came back — the next check must not trust the answer from before that
    happened (specs/trading-mcp-upstream-access, "Gateway zmienia środowisko przy
    odzyskanym połączeniu")."""
    route = respx.get(f"{BASE}/capabilities").mock(
        return_value=httpx.Response(200, json={"environment": "demo"})
    )
    await client.ensure_demo_environment()
    assert route.call_count == 1

    respx.get(f"{BASE}/positions").mock(side_effect=httpx.ConnectError("dropped"))
    with pytest.raises(GatewayUnavailable):
        await client.get("/positions")

    await client.ensure_demo_environment()
    assert route.call_count == 2
    await client.aclose()
