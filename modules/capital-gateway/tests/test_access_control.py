"""specs/capital-access-control — who may call this module, and what it never shows.

`docs_url` / `openapi_url` are baked into the FastAPI app object at import time (they
are constructor arguments, not per-request state), so the production variant needs a
fresh import with `GATEWAY_ENV` already set — see `_imported_with`.
"""

from __future__ import annotations

import importlib
import sys

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from capital_gateway.config import API_KEY_HEADER, DEMO_BASE_URL

API = f"{DEMO_BASE_URL}/api/v1"
GATEWAY_KEY = "gateway-caller-key"


@pytest.fixture(autouse=True)
def _credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAPITAL_API_KEY", "super-secret-key")
    monkeypatch.setenv("CAPITAL_IDENTIFIER", "me@example.com")
    monkeypatch.setenv("CAPITAL_PASSWORD", "hunter2")
    monkeypatch.setenv("GATEWAY_API_KEY", GATEWAY_KEY)


@pytest.fixture
def client() -> TestClient:
    from capital_gateway.app import app

    return TestClient(app)


def _imported_with(monkeypatch: pytest.MonkeyPatch, **env: str):
    """Reimport `capital_gateway.app` with the given environment set, then restore the
    module every other test sees to the non-production variant."""
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    module = importlib.reload(sys.modules["capital_gateway.app"])
    yield module.app
    for key in env:
        monkeypatch.delenv(key, raising=False)
    importlib.reload(sys.modules["capital_gateway.app"])


@pytest.fixture
def production_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    gen = _imported_with(monkeypatch, GATEWAY_ENV="production")
    app = next(gen)
    yield TestClient(app)
    next(gen, None)


# --- every call carries a credential ---


def test_a_request_without_the_header_is_refused(client: TestClient) -> None:
    with client:
        response = client.get("/positions")

    assert response.status_code == 401


def test_a_request_with_the_wrong_key_is_refused(client: TestClient) -> None:
    with client:
        response = client.get("/positions", headers={API_KEY_HEADER: "not-the-key"})

    assert response.status_code == 401


def test_neither_refusal_reaches_the_provider(client: TestClient) -> None:
    with respx.mock:
        route = respx.get(f"{API}/positions")
        with client:
            client.get("/positions")
            client.get("/positions", headers={API_KEY_HEADER: "wrong"})
        assert route.call_count == 0


@respx.mock
def test_the_right_key_is_accepted(client: TestClient) -> None:
    respx.post(f"{API}/session").mock(
        return_value=httpx.Response(200, headers={"CST": "c", "X-SECURITY-TOKEN": "s"}, json={})
    )
    respx.get(f"{API}/positions").mock(return_value=httpx.Response(200, json={"positions": []}))

    with client:
        response = client.get("/positions", headers={API_KEY_HEADER: GATEWAY_KEY})

    assert response.status_code == 200


def test_a_websocket_without_the_header_is_closed(client: TestClient) -> None:
    with (
        client,
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws/stream?symbol=US100", headers={}),
    ):
        pass


def test_a_websocket_with_the_wrong_key_is_closed(client: TestClient) -> None:
    with (
        client,
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(
            "/ws/stream?symbol=US100", headers={API_KEY_HEADER: "not-the-key"}
        ),
    ):
        pass


# --- the health probe is the one exception ---


def test_the_health_probe_needs_no_key(client: TestClient) -> None:
    with client:
        response = client.get("/")

    assert response.status_code == 200


def test_the_health_probe_names_nothing_sensitive(client: TestClient) -> None:
    with client:
        body = client.get("/").json()

    assert "account" not in body
    assert "session" not in body
    assert set(body) == {"service", "status"}


# --- without a configured key, the module refuses to start ---


def test_start_without_a_gateway_key_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GATEWAY_API_KEY", raising=False)
    from capital_gateway.config import Settings

    # `_env_file=None`: Settings reads env_file=".env" by default, so a developer's own
    # .env would still satisfy the required field and this test would pass only where the
    # misconfiguration it checks for cannot happen. Disabling the file here isolates the
    # check to the environment actually being deleted from, above.
    with pytest.raises(ValueError):
        Settings(_env_file=None)  # type: ignore[call-arg]


# --- the schema is off in production ---


def test_docs_are_published_off_production(client: TestClient) -> None:
    with client:
        response = client.get("/openapi.json", headers={API_KEY_HEADER: GATEWAY_KEY})

    assert response.status_code == 200
    assert response.json()["paths"]


def test_docs_are_absent_in_production(production_client: TestClient) -> None:
    with production_client:
        schema_response = production_client.get(
            "/openapi.json", headers={API_KEY_HEADER: GATEWAY_KEY}
        )
        docs_response = production_client.get("/docs", headers={API_KEY_HEADER: GATEWAY_KEY})

    assert schema_response.status_code == 404
    assert docs_response.status_code == 404


# --- the key itself never leaks ---


def test_a_refusal_does_not_echo_the_key_back(client: TestClient) -> None:
    with client:
        response = client.get("/positions", headers={API_KEY_HEADER: "guess-1"})

    assert "guess-1" not in response.text
    assert GATEWAY_KEY not in response.text
