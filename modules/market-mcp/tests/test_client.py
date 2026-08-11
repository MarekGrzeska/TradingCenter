from __future__ import annotations

import httpx
import pytest
import respx

from market_mcp.client import UpstreamClient, UpstreamWriteRejected
from market_mcp.config import Settings

BASE = "http://127.0.0.1:8020"


@pytest.fixture
def client(settings: Settings) -> UpstreamClient:
    return UpstreamClient(settings)


@respx.mock
async def test_get_reaches_market_data(client: UpstreamClient) -> None:
    route = respx.get(f"{BASE}/pairs").mock(return_value=httpx.Response(200, json=[]))

    response = await client.get("/pairs")

    assert route.called
    assert response.status_code == 200
    await client.aclose()


@respx.mock
async def test_compute_indicators_is_allowed(client: UpstreamClient) -> None:
    route = respx.post(f"{BASE}/indicators/US100").mock(
        return_value=httpx.Response(200, json={"results": []})
    )

    response = await client.compute_indicators("US100", {"resolution": "MINUTE", "specs": []})

    assert route.called
    assert response.status_code == 200
    await client.aclose()


async def test_delete_is_rejected_before_any_request(client: UpstreamClient) -> None:
    with pytest.raises(UpstreamWriteRejected):
        await client._request("DELETE", "/pairs/US100")
    await client.aclose()


async def test_post_outside_indicators_is_rejected(client: UpstreamClient) -> None:
    with pytest.raises(UpstreamWriteRejected):
        await client._request("POST", "/pairs")
    await client.aclose()


async def test_post_with_nested_indicators_path_is_rejected(client: UpstreamClient) -> None:
    # `/indicators/{symbol}` only — a path with anything past the symbol is not the
    # one write-shaped exception the client carves out.
    with pytest.raises(UpstreamWriteRejected):
        await client._request("POST", "/indicators/US100/extra")
    await client.aclose()
