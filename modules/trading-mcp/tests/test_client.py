"""client.py: authentication, retry-vs-no-retry, and error mapping."""

from __future__ import annotations

import httpx
import pytest
import respx

from trading_mcp.client import GATEWAY_KEY_HEADER, GatewayClient
from trading_mcp.config import Settings
from trading_mcp.errors import GatewayRefused, GatewayUnavailable

BASE = "http://127.0.0.1:8010"


@pytest.fixture
def client(settings: Settings) -> GatewayClient:
    return GatewayClient(settings)


@respx.mock
async def test_every_request_carries_the_gateway_key(client: GatewayClient) -> None:
    route = respx.get(f"{BASE}/positions").mock(return_value=httpx.Response(200, json=[]))

    await client.get("/positions")

    assert route.calls.last.request.headers[GATEWAY_KEY_HEADER] == "test-gateway-key"
    await client.aclose()


@respx.mock
async def test_a_single_5xx_read_is_retried_and_can_succeed(client: GatewayClient) -> None:
    route = respx.get(f"{BASE}/positions").mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json=[])]
    )

    result = await client.get("/positions")

    assert result == []
    assert route.call_count == 2
    await client.aclose()


@respx.mock
async def test_a_persistent_5xx_read_is_refused_after_one_retry(client: GatewayClient) -> None:
    route = respx.get(f"{BASE}/positions").mock(
        return_value=httpx.Response(503, json={"detail": "unavailable"})
    )

    with pytest.raises(GatewayRefused) as excinfo:
        await client.get("/positions")

    assert excinfo.value.status_code == 503
    assert route.call_count == 2
    await client.aclose()


@respx.mock
async def test_a_write_is_never_retried_on_5xx(client: GatewayClient) -> None:
    route = respx.post(f"{BASE}/orders").mock(
        return_value=httpx.Response(503, json={"detail": "unavailable"})
    )

    with pytest.raises(GatewayRefused):
        await client.write("POST", "/orders", json={"symbol": "GOLD"})

    assert route.call_count == 1
    await client.aclose()


@respx.mock
async def test_a_write_is_never_retried_after_a_timeout(client: GatewayClient) -> None:
    route = respx.post(f"{BASE}/orders").mock(side_effect=httpx.ReadTimeout("timed out"))

    with pytest.raises(GatewayUnavailable):
        await client.write("POST", "/orders", json={"symbol": "GOLD"})

    assert route.call_count == 1
    await client.aclose()


@respx.mock
async def test_a_4xx_is_a_refusal_naming_the_detail(client: GatewayClient) -> None:
    respx.post(f"{BASE}/orders").mock(
        return_value=httpx.Response(422, json={"detail": "level is required for LIMIT/STOP"})
    )

    with pytest.raises(GatewayRefused, match="level is required"):
        await client.write("POST", "/orders", json={"symbol": "GOLD"})
    await client.aclose()


@respx.mock
async def test_timeout_is_a_gateway_unavailable(client: GatewayClient) -> None:
    respx.get(f"{BASE}/positions").mock(side_effect=httpx.ReadTimeout("timed out"))

    with pytest.raises(GatewayUnavailable, match="did not respond"):
        await client.get("/positions")
    await client.aclose()


@respx.mock
async def test_unreachable_gateway_is_a_gateway_unavailable(client: GatewayClient) -> None:
    respx.get(f"{BASE}/positions").mock(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(GatewayUnavailable, match="unreachable"):
        await client.get("/positions")
    await client.aclose()
