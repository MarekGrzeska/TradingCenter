"""specs/capital-access-control — who may call this module, and what it never shows.

`docs_url` / `openapi_url` are baked into the FastAPI app object at import time (they
are constructor arguments, not per-request state), so the production variant needs a
fresh import with `GATEWAY_ENV` already set — see `_imported_with`.
"""

from __future__ import annotations

import base64
import importlib
import json
import sys

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from capital_gateway.caller_access import PRINCIPAL_HEADER
from capital_gateway.config import API_KEY_HEADER, DEMO_BASE_URL

API = f"{DEMO_BASE_URL}/api/v1"
GATEWAY_KEY = "gateway-caller-key"
TERMINAL_APP_ID = "11111111-2222-3333-4444-555555555555"


def _principal(application_id: str) -> str:
    """What the platform authenticator puts on a request it let through: the token's own
    claims, base64'd. Built rather than fixtured, so a test can name any application."""
    blob = json.dumps({"claims": [{"typ": "azp", "val": application_id}]})
    return base64.b64encode(blob.encode()).decode()


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


# --- the second credential: a browser the platform authenticated ---


@pytest.fixture
def with_terminal(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """The gateway as it stands after the operator's apply: one application allowed in
    without the shared key."""
    monkeypatch.setenv("BROWSER_CALLER_APPLICATION_IDS", f'["{TERMINAL_APP_ID}"]')
    for module in [m for m in sys.modules if m.startswith("capital_gateway")]:
        del sys.modules[module]
    from capital_gateway.app import app

    return TestClient(app)


@respx.mock
def test_a_recognised_application_reaches_the_account_without_the_key(
    with_terminal: TestClient,
) -> None:
    # specs/capital-access-control, "Żądanie od uwierzytelnionej aplikacji bez klucza"
    respx.post(f"{API}/session").mock(
        return_value=httpx.Response(200, headers={"CST": "c", "X-SECURITY-TOKEN": "s"}, json={})
    )
    respx.get(f"{API}/session").mock(return_value=httpx.Response(200, json={"accountId": "a1"}))
    respx.get(f"{API}/accounts").mock(return_value=httpx.Response(200, json={"accounts": []}))

    with with_terminal as client:
        response = client.get("/accounts", headers={PRINCIPAL_HEADER: _principal(TERMINAL_APP_ID)})

    assert response.status_code == 200


def test_a_recognised_application_may_not_place_an_order(with_terminal: TestClient) -> None:
    """specs/capital-access-control, "Terminal próbuje złożyć zlecenie" — through the
    platform's door and still not a trader."""
    with respx.mock:
        route = respx.post(f"{API}/positions")
        with with_terminal as client:
            response = client.post(
                "/orders",
                json={"symbol": "GOLD", "direction": "BUY", "size": 1, "order_type": "MARKET"},
                headers={PRINCIPAL_HEADER: _principal(TERMINAL_APP_ID)},
            )

    assert response.status_code == 403
    assert not route.called


def test_a_path_outside_the_record_is_refused_by_default(with_terminal: TestClient) -> None:
    # specs/capital-access-control, "Nowa trasa nie staje się dostępna sama"
    with with_terminal as client:
        response = client.get(
            "/instruments/GOLD/terms", headers={PRINCIPAL_HEADER: _principal(TERMINAL_APP_ID)}
        )

    assert response.status_code == 403


def test_an_unrecognised_application_is_refused(with_terminal: TestClient) -> None:
    # specs/capital-access-control, "Żądanie od uwierzytelnionej aplikacji spoza listy"
    with with_terminal as client:
        response = client.get(
            "/accounts", headers={PRINCIPAL_HEADER: _principal("99999999-0000-0000-0000-000000000000")}
        )

    assert response.status_code == 401


def test_a_principal_header_that_is_not_an_identity_is_refused(with_terminal: TestClient) -> None:
    """A blob that will not decode is a header to ignore, not a caller to trust."""
    with with_terminal as client:
        response = client.get("/accounts", headers={PRINCIPAL_HEADER: "not-base64-at-all"})

    assert response.status_code == 401


def test_with_no_application_configured_the_door_is_shut(client: TestClient) -> None:
    """The default everywhere but production: an empty list means nobody comes this way,
    not everybody."""
    with client:
        response = client.get("/accounts", headers={PRINCIPAL_HEADER: _principal(TERMINAL_APP_ID)})

    assert response.status_code == 401


@respx.mock
def test_the_key_still_reaches_everything(with_terminal: TestClient) -> None:
    """The modules' own path, unchanged by any of this."""
    respx.post(f"{API}/session").mock(
        return_value=httpx.Response(200, headers={"CST": "c", "X-SECURITY-TOKEN": "s"}, json={})
    )
    respx.get(f"{API}/positions").mock(return_value=httpx.Response(200, json={"positions": []}))

    with with_terminal as client:
        response = client.get("/positions", headers={API_KEY_HEADER: GATEWAY_KEY})

    assert response.status_code == 200
