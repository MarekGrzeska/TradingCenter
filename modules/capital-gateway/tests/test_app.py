"""The published surface: what the schema covers, and what never leaves the process."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from capital_gateway.app import app
from capital_gateway.config import DEMO_BASE_URL
from tests.conftest import load_fixture

API = f"{DEMO_BASE_URL}/api/v1"

SECRETS = {
    "api_key": "super-secret-key",
    "identifier": "me@example.com",
    "password": "hunter2",
    "cst": "cst-token-value",
    "security_token": "x-security-token-value",
}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("CAPITAL_API_KEY", SECRETS["api_key"])
    monkeypatch.setenv("CAPITAL_IDENTIFIER", SECRETS["identifier"])
    monkeypatch.setenv("CAPITAL_PASSWORD", SECRETS["password"])
    return TestClient(app)


def mock_login() -> None:
    respx.post(f"{API}/session").mock(
        return_value=httpx.Response(
            200,
            headers={"CST": SECRETS["cst"], "X-SECURITY-TOKEN": SECRETS["security_token"]},
            json={},
        )
    )
    respx.get(f"{API}/session").mock(return_value=httpx.Response(200, json={"accountId": "a1"}))


# --- the schema ---


def test_every_route_appears_in_the_published_schema(client: TestClient) -> None:
    with client:
        schema = client.get("/openapi.json").json()

    documented = set(schema["paths"])
    expected = {
        "/",
        "/capabilities",
        "/accounts",
        "/accounts/active",
        "/asset-classes",
        "/instruments",
        "/instruments/search",
        "/instruments/{symbol}/candles",
        "/instruments/{symbol}/history",
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
    # The route accepted the anchor and reached the provider at all — the window
    # arithmetic itself is covered in test_history.py; this only proves the parameter is
    # wired from the query string through to the adapter.
    request_made = prices.calls.last.request
    assert "2024-01-14" in str(request_made.url) or "2024-01-15" in str(request_made.url)


def test_the_asset_classes_are_published(client: TestClient) -> None:
    with client:
        body = client.get("/asset-classes").json()

    assert set(body) == {"SHARES", "INDICES", "CRYPTO", "CURRENCIES", "COMMODITIES", "OTHER"}


# --- nothing leaks ---


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


# --- the stream ---


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
