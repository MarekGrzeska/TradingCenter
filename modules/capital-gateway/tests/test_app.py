"""The published surface: what the schema covers, and what never leaves the process."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from capital_gateway.app import app
from capital_gateway.config import API_KEY_HEADER, DEMO_BASE_URL
from tests.conftest import load_fixture

API = f"{DEMO_BASE_URL}/api/v1"

SECRETS = {
    "api_key": "super-secret-key",
    "identifier": "me@example.com",
    "password": "hunter2",
    "cst": "cst-token-value",
    "security_token": "x-security-token-value",
    "gateway_key": "gateway-caller-key",
}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("CAPITAL_API_KEY", SECRETS["api_key"])
    monkeypatch.setenv("CAPITAL_IDENTIFIER", SECRETS["identifier"])
    monkeypatch.setenv("CAPITAL_PASSWORD", SECRETS["password"])
    monkeypatch.setenv("GATEWAY_API_KEY", SECRETS["gateway_key"])
    # Every route past "/" requires this header — see test_access_control.py for the middleware.
    # A default header here keeps every other test in this file about the route it names.
    return TestClient(app, headers={API_KEY_HEADER: SECRETS["gateway_key"]})


def mock_login() -> None:
    respx.post(f"{API}/session").mock(
        return_value=httpx.Response(
            200,
            headers={"CST": SECRETS["cst"], "X-SECURITY-TOKEN": SECRETS["security_token"]},
            json={},
        )
    )
    respx.get(f"{API}/session").mock(return_value=httpx.Response(200, json={"accountId": "a1"}))



def test_every_route_appears_in_the_published_schema(client: TestClient) -> None:
    with client:
        schema = client.get("/openapi.json").json()

    documented = set(schema["paths"])
    expected = {
        "/",
        "/capabilities",
        "/accounts",
        "/accounts/active",
        "/accounts/top-up",
        "/asset-classes",
        "/instruments",
        "/instruments/search",
        "/instruments/{symbol}/candles",
        "/instruments/{symbol}/history",
        "/instruments/{symbol}/terms",
        "/positions",
        "/orders",
        "/positions/{position_id}",
        "/working-orders",
        "/working-orders/{order_id}",
    }
    assert expected <= documented
    # The WebSocket is absent by necessity, not by oversight: OpenAPI cannot describe it.
    assert "/ws/stream" not in documented


@respx.mock
def test_capabilities_name_the_environment(client: TestClient) -> None:
    mock_login()
    with client:
        body = client.get("/capabilities").json()

    assert body["environment"] == "demo"
    assert body["has_streaming"] is True


@respx.mock
def test_an_unknown_asset_class_is_refused_by_naming_the_known_ones(client: TestClient) -> None:
    mock_login()

    with client:
        response = client.get("/instruments", params={"asset_class": "STONKS"})

    assert response.status_code == 422
    detail = response.json()["detail"]
    # The caller's next move is to pick a different class, so the refusal hands them the
    # ones there are rather than only rejecting the one they tried.
    assert "STONKS" in detail
    assert "CRYPTO" in detail and "SHARES" in detail


@respx.mock
def test_a_before_parameter_anchors_the_deep_read_in_the_past(client: TestClient) -> None:
    mock_login()
    prices = respx.get(f"{API}/prices/GOLD")
    prices.mock(
        return_value=httpx.Response(
            200, json={"prices": [{"snapshotTimeUTC": "2024-01-15T00:00:00"}]}
        )
    )

    with client:
        response = client.get(
            "/instruments/GOLD/history",
            params={"resolution": "MINUTE_5", "bars": 2, "before": "2024-01-15T00:00:00Z"},
        )

    assert response.status_code == 200
    # The route accepted the anchor and reached the provider at all; the window arithmetic is
    # covered in test_history.py. This only proves the parameter is wired through to the adapter.
    request_made = prices.calls.last.request
    assert "2024-01-14" in str(request_made.url) or "2024-01-15" in str(request_made.url)


@respx.mock
def test_an_after_parameter_bounds_the_deep_read_in_the_past(client: TestClient) -> None:
    mock_login()
    prices = respx.get(f"{API}/prices/GOLD")
    prices.mock(
        return_value=httpx.Response(
            200,
            json={
                "prices": [
                    {"snapshotTimeUTC": "2024-01-01T00:00:00"},  # older than the floor
                    {"snapshotTimeUTC": "2024-01-15T00:00:00"},
                ]
            },
        )
    )

    with client:
        response = client.get(
            "/instruments/GOLD/history",
            params={
                "resolution": "MINUTE_5",
                "bars": 1000,
                "before": "2024-01-15T00:00:00Z",
                # Inside the window 1000 five-minute candles would otherwise span
                # (~3.5 days), so it is the floor that decides where the request starts.
                "after": "2024-01-14T00:00:00Z",
            },
        )

    assert response.status_code == 200
    body = response.json()
    # The candle from before the floor came back inside the provider's page and was
    # dropped; only the one at or after it survives.
    assert [c["ts"] for c in body["candles"]] == ["2024-01-15T00:00:00Z"]
    # And the window asked for never reached past the floor in the first place.
    assert "from=2024-01-14T00%3A00%3A00" in str(prices.calls.last.request.url)


def test_the_asset_classes_are_published(client: TestClient) -> None:
    with client:
        body = client.get("/asset-classes").json()

    assert set(body) == {"SHARES", "INDICES", "CRYPTO", "CURRENCIES", "COMMODITIES", "OTHER"}



@respx.mock
def test_no_response_carries_a_credential_or_a_session_token(client: TestClient) -> None:
    mock_login()
    respx.get(f"{API}/accounts").mock(
        return_value=httpx.Response(200, json=load_fixture("accounts.json"))
    )
    respx.get(f"{API}/prices/GOLD").mock(
        return_value=httpx.Response(200, json=load_fixture("prices_gold.json"))
    )

    with client:
        bodies = [
            client.get("/capabilities").text,
            client.get("/accounts").text,
            client.get("/instruments/GOLD/candles").text,
            client.get("/openapi.json").text,
        ]

    for body in bodies:
        for secret in SECRETS.values():
            assert secret not in body


@respx.mock
def test_a_provider_refusal_becomes_a_stated_status_not_a_stack_trace(
    client: TestClient,
) -> None:
    mock_login()
    respx.get(f"{API}/prices/NOPE").mock(
        return_value=httpx.Response(404, json={"errorCode": "error.not-found.epic"})
    )

    with client:
        response = client.get("/instruments/NOPE/candles")

    assert response.status_code == 404
    assert "NOPE" in response.json()["detail"]


@respx.mock
def test_instrument_terms_come_from_the_market_detail(client: TestClient) -> None:
    mock_login()
    market = respx.get(f"{API}/markets/GOLD")
    market.mock(return_value=httpx.Response(200, json=load_fixture("market_gold.json")))

    with client:
        response = client.get("/instruments/GOLD/terms")

    assert response.status_code == 200
    body = response.json()
    assert body["margin_factor"] == 100
    assert body["margin_factor_unit"] == "PERCENTAGE"
    assert body["size_increment"] == 0.01
    # One request, the same one `_market_open` makes — this route reads the rest of an
    # answer the module was already paying for.
    assert market.call_count == 1


@respx.mock
def test_terms_for_an_instrument_the_provider_does_not_know_name_the_symbol(
    client: TestClient,
) -> None:
    mock_login()
    respx.get(f"{API}/markets/NOPE").mock(
        return_value=httpx.Response(404, json={"errorCode": "error.not-found.epic"})
    )

    with client:
        response = client.get("/instruments/NOPE/terms")

    assert response.status_code == 404
    assert "NOPE" in response.json()["detail"]


@respx.mock
def test_a_resting_order_without_a_level_is_refused_by_the_schema(client: TestClient) -> None:
    mock_login()
    orders = respx.post(f"{API}/workingorders")

    with client:
        response = client.post(
            "/orders",
            json={"symbol": "GOLD", "direction": "BUY", "size": 0.01, "order_type": "LIMIT"},
        )

    assert response.status_code == 422
    # Refused here, so the provider was never asked.
    assert orders.call_count == 0



@pytest.mark.parametrize(
    "query",
    ["", "?resolution=MINUTE_5", "?symbol=US100&resolution=FORTNIGHT"],
)
def test_a_stream_missing_a_symbol_or_naming_a_bad_resolution_is_refused(
    client: TestClient, query: str
) -> None:
    # Refused before the handshake completes, so connecting itself raises rather than
    # handing back a socket that closes a moment later.
    with (
        client,
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(f"/ws/stream{query}"),
    ):
        pass


@respx.mock
def test_a_subscriber_hears_the_room_state_and_no_tokens(client: TestClient) -> None:
    mock_login()

    with client, client.websocket_connect("/ws/stream?symbol=US100&resolution=MINUTE_5") as ws:
        first = ws.receive_json()

    assert first["kind"] == "status"
    # The stream borrows the REST session, so this is exactly where tokens would leak.
    assert SECRETS["cst"] not in json.dumps(first)
    assert SECRETS["security_token"] not in json.dumps(first)


# One of the ids `accounts.json` carries, so a read-back can find it.
ACTIVE_ACCOUNT_ID = "325778595166630174"


@respx.mock
def test_a_top_up_moves_the_balance_and_answers_with_the_account(client: TestClient) -> None:
    # specs/capital-session, "Dosypanie środków"
    mock_login()
    # The session names an account the fixture actually holds — the top-up answers with the
    # active one, read back after the adjustment.
    respx.get(f"{API}/session").mock(
        return_value=httpx.Response(200, json={"accountId": ACTIVE_ACCOUNT_ID})
    )
    sent: list[dict] = []

    def record(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"successful": True})

    respx.post(f"{API}/accounts/topUp").mock(side_effect=record)
    respx.get(f"{API}/accounts").mock(
        return_value=httpx.Response(200, json=load_fixture("accounts.json"))
    )

    with client:
        response = client.post("/accounts/top-up", json={"amount": 5000})

    assert response.status_code == 200
    assert sent == [{"amount": 5000.0}]
    # The account it answers with is the active one, which is what the caller just changed.
    assert response.json()["active"] is True


@respx.mock
def test_taking_funds_away_travels_the_same_route(client: TestClient) -> None:
    # specs/capital-session, "Zabranie środków" — a thin account is a setup, not a mistake.
    mock_login()
    # The session names an account the fixture actually holds — the top-up answers with the
    # active one, read back after the adjustment.
    respx.get(f"{API}/session").mock(
        return_value=httpx.Response(200, json={"accountId": ACTIVE_ACCOUNT_ID})
    )
    sent: list[dict] = []

    def record(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"successful": True})

    respx.post(f"{API}/accounts/topUp").mock(side_effect=record)
    respx.get(f"{API}/accounts").mock(
        return_value=httpx.Response(200, json=load_fixture("accounts.json"))
    )

    with client:
        response = client.post("/accounts/top-up", json={"amount": -2500})

    assert response.status_code == 200
    assert sent == [{"amount": -2500.0}]


@respx.mock
def test_a_refused_top_up_carries_the_providers_reason(client: TestClient) -> None:
    # specs/capital-session, "Dostawca odmawia korekty" — the ceiling, the range and the
    # daily count are the provider's to enforce, and its words are what reach the caller.
    mock_login()
    respx.post(f"{API}/accounts/topUp").mock(
        return_value=httpx.Response(
            400, json={"errorCode": "error.request.top.up.balance.exceeded"}
        )
    )

    with client:
        response = client.post("/accounts/top-up", json={"amount": 400000})

    assert response.status_code == 400
    assert "top.up.balance.exceeded" in response.text


@respx.mock
def test_a_top_up_of_zero_never_reaches_the_provider(client: TestClient) -> None:
    # The one amount that means nothing, and the only limit this module keeps of its own.
    mock_login()
    route = respx.post(f"{API}/accounts/topUp")

    with client:
        response = client.post("/accounts/top-up", json={"amount": 0})

    assert response.status_code == 422
    assert not route.called


def test_switching_accounts_says_it_drops_the_stream(client: TestClient) -> None:
    """specs/capital-session, "Strumień po przełączeniu konta" — a route description is contract,
    not commentary: the consequence of this call lands in a different module entirely."""
    with client:
        schema = client.get("/openapi.json").json()

    description = schema["paths"]["/accounts/active"]["put"]["description"]
    assert "stream" in description.lower()
