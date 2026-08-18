"""`ensure_demo_environment()`: refuse anything but the demo account, before the port
opens (specs/trading-mcp-upstream-access, "Moduł pracuje wyłącznie na rachunku
demonstracyjnym").

The three-state cache this file used to test is gone, and so is the re-check in front of
every write. What it was defending against — a gateway that changed environment under a
running process — it could not actually detect: the field it compared was a literal in
the gateway's own source, so the check only ever proved the gateway was answering. The
gateway derives that field now, and this module still refuses to listen until it has read
it (`openspec/changes/hot-paths-stop-paying-twice/design.md`, D4).
"""

from __future__ import annotations

import httpx
import pytest
import respx

from trading_mcp.client import GatewayClient
from trading_mcp.config import Settings
from trading_mcp.errors import GatewayRefused, GatewayUnavailable, NotDemoEnvironment

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
async def test_a_missing_environment_field_is_refused_too(client: GatewayClient) -> None:
    """An answer that does not name the environment is not an answer that it is demo."""
    respx.get(f"{BASE}/capabilities").mock(return_value=httpx.Response(200, json={}))

    with pytest.raises(NotDemoEnvironment):
        await client.ensure_demo_environment()
    await client.aclose()


@respx.mock
async def test_an_unreachable_gateway_stops_the_start(client: GatewayClient) -> None:
    """`__main__` lets this out of `_serve`, so the process exits instead of listening
    with the environment unchecked."""
    respx.get(f"{BASE}/capabilities").mock(side_effect=httpx.ConnectError("dropped"))

    with pytest.raises(GatewayUnavailable):
        await client.ensure_demo_environment()
    await client.aclose()


@respx.mock
async def test_a_gateway_refusal_stops_the_start(client: GatewayClient) -> None:
    respx.get(f"{BASE}/capabilities").mock(
        return_value=httpx.Response(401, json={"detail": "missing or invalid caller key"})
    )

    with pytest.raises(GatewayRefused):
        await client.ensure_demo_environment()
    await client.aclose()


@respx.mock
async def test_nothing_is_remembered_between_asks(client: GatewayClient) -> None:
    """There is no cache left to go stale — the answer is read at the one moment it is
    asked for, and that moment is before the port opens."""
    route = respx.get(f"{BASE}/capabilities").mock(
        return_value=httpx.Response(200, json={"environment": "demo"})
    )

    await client.ensure_demo_environment()
    await client.ensure_demo_environment()

    assert route.call_count == 2
    await client.aclose()


@respx.mock
async def test_an_error_on_another_call_costs_nothing_later(client: GatewayClient) -> None:
    """The measured cost of the old arrangement: a gateway restarted behind App Service
    answers 503, which set the cache to unverified, and every write for the rest of the
    process's life then paid for a second round trip."""
    respx.get(f"{BASE}/capabilities").mock(
        return_value=httpx.Response(200, json={"environment": "demo"})
    )
    await client.ensure_demo_environment()

    respx.get(f"{BASE}/positions").mock(return_value=httpx.Response(503, json={"detail": "down"}))
    with pytest.raises(GatewayRefused):
        await client.get("/positions")

    orders = respx.post(f"{BASE}/orders").mock(return_value=httpx.Response(200, json={}))
    await client.write("POST", "/orders", json={"symbol": "GOLD"})

    assert orders.call_count == 1
    await client.aclose()
