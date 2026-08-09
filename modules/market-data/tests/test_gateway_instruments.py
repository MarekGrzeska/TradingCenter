"""specs/market-data-api: the catalogue proxy methods on GatewayInstruments.

Unread pass-through is the whole point — these assert the request reaches the gateway's
real routes and the gateway's response comes back exactly as it arrived, plus the caller
key on every request.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from market_data.errors import GatewayRefused, GatewayUnreachable, UnreadablePayload
from market_data.gateway import GATEWAY_KEY_HEADER, GatewayInstruments

BASE_URL = "http://gateway.test:8010"


@pytest.fixture
async def gw():
    async with httpx.AsyncClient(headers={GATEWAY_KEY_HEADER: "the-caller-key"}) as client:
        yield GatewayInstruments(BASE_URL, client)


@respx.mock
async def test_the_catalogue_comes_back_unreshaped(gw: GatewayInstruments) -> None:
    body = {"instruments": [{"symbol": "GOLD"}], "count": 1, "truncated": False}
    route = respx.get(f"{BASE_URL}/instruments").mock(return_value=httpx.Response(200, json=body))

    result = await gw.catalogue(None, None)

    assert result == body
    assert route.calls.last.request.headers[GATEWAY_KEY_HEADER] == "the-caller-key"


@respx.mock
async def test_the_catalogue_forwards_max_nodes_and_asset_class(gw: GatewayInstruments) -> None:
    route = respx.get(f"{BASE_URL}/instruments").mock(
        return_value=httpx.Response(200, json={"instruments": [], "count": 0, "truncated": False})
    )

    await gw.catalogue(50, "CRYPTO")

    sent = route.calls.last.request.url.params
    assert sent["max_nodes"] == "50"
    assert sent["asset_class"] == "CRYPTO"


@respx.mock
async def test_a_search_comes_back_unreshaped(gw: GatewayInstruments) -> None:
    hits = [{"symbol": "GOLD", "name": "Gold", "asset_class": "COMMODITIES", "tradeable": True}]
    respx.get(f"{BASE_URL}/instruments/search").mock(return_value=httpx.Response(200, json=hits))

    assert await gw.search("gold") == hits


@respx.mock
async def test_asset_classes_come_back_unreshaped(gw: GatewayInstruments) -> None:
    respx.get(f"{BASE_URL}/asset-classes").mock(
        return_value=httpx.Response(200, json=["CRYPTO", "SHARES"])
    )

    assert await gw.asset_classes() == ["CRYPTO", "SHARES"]


@respx.mock
@pytest.mark.parametrize(
    "method,call",
    [
        ("catalogue", lambda gw: gw.catalogue(None, None)),
        ("search", lambda gw: gw.search("gold")),
        ("asset_classes", lambda gw: gw.asset_classes()),
    ],
)
async def test_a_401_is_a_refusal_not_an_empty_answer(gw: GatewayInstruments, method, call) -> None:
    respx.get(f"{BASE_URL}/instruments").mock(
        return_value=httpx.Response(401, json={"detail": "missing or invalid caller key"})
    )
    respx.get(f"{BASE_URL}/instruments/search").mock(
        return_value=httpx.Response(401, json={"detail": "missing or invalid caller key"})
    )
    respx.get(f"{BASE_URL}/asset-classes").mock(
        return_value=httpx.Response(401, json={"detail": "missing or invalid caller key"})
    )

    with pytest.raises(GatewayRefused) as err:
        await call(gw)

    assert err.value.status_code == 401


@respx.mock
async def test_an_unreachable_gateway_is_named_as_such(gw: GatewayInstruments) -> None:
    respx.get(f"{BASE_URL}/instruments").mock(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(GatewayUnreachable):
        await gw.catalogue(None, None)


@respx.mock
async def test_a_search_that_is_not_a_list_is_drift_not_silence(gw: GatewayInstruments) -> None:
    respx.get(f"{BASE_URL}/instruments/search").mock(
        return_value=httpx.Response(200, json={"not": "a list"})
    )

    with pytest.raises(UnreadablePayload):
        await gw.search("gold")
