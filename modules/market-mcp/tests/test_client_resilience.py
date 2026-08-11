"""Task 4.3: one retry on a server error, a timeout and an unreachable archive both
read as `ToolRefusal` rather than an unhandled exception, plus 4.8's concurrency gate.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from market_mcp.client import UpstreamClient
from market_mcp.config import Settings
from market_mcp.errors import ToolRefusal

BASE = "http://127.0.0.1:8020"


@pytest.fixture
def client(settings: Settings) -> UpstreamClient:
    return UpstreamClient(settings)


@respx.mock
async def test_a_single_5xx_is_retried_and_can_succeed(client: UpstreamClient) -> None:
    route = respx.get(f"{BASE}/pairs").mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json=[])]
    )

    response = await client.get("/pairs")

    assert response.status_code == 200
    assert route.call_count == 2
    await client.aclose()


@respx.mock
async def test_a_persistent_5xx_is_returned_after_one_retry(client: UpstreamClient) -> None:
    route = respx.get(f"{BASE}/pairs").mock(return_value=httpx.Response(503))

    response = await client.get("/pairs")

    assert response.status_code == 503
    assert route.call_count == 2  # exactly one retry, not a loop
    await client.aclose()


@respx.mock
async def test_a_4xx_is_not_retried(client: UpstreamClient) -> None:
    route = respx.get(f"{BASE}/pairs").mock(return_value=httpx.Response(422, json={"detail": "x"}))

    response = await client.get("/pairs")

    assert response.status_code == 422
    assert route.call_count == 1
    await client.aclose()


@respx.mock
async def test_timeout_is_a_tool_refusal_naming_the_failure(client: UpstreamClient) -> None:
    respx.get(f"{BASE}/pairs").mock(side_effect=httpx.ReadTimeout("timed out"))

    with pytest.raises(ToolRefusal, match="did not respond"):
        await client.get("/pairs")
    await client.aclose()


@respx.mock
async def test_unreachable_archive_is_a_tool_refusal(client: UpstreamClient) -> None:
    respx.get(f"{BASE}/pairs").mock(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(ToolRefusal, match="unreachable"):
        await client.get("/pairs")
    await client.aclose()


@respx.mock
async def test_concurrent_requests_are_capped(client: UpstreamClient) -> None:
    in_flight = 0
    peak = 0

    async def _handler(request: httpx.Request) -> httpx.Response:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return httpx.Response(200, json=[])

    respx.get(f"{BASE}/pairs").mock(side_effect=_handler)

    await asyncio.gather(*[client.get("/pairs") for _ in range(20)])

    assert peak <= 8  # MAX_CONCURRENT_UPSTREAM_REQUESTS
    assert peak > 1  # actually ran concurrently, not serialized by something else
    await client.aclose()
