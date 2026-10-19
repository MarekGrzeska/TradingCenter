"""move-from-azure-to-vps — the gateway behind the edge proxy with no platform authenticator: an Entra token for what
came through the edge, the shared key for what came from another service. The token check itself is tested in
`packages/tc-entra-auth`; here is only that this module's door, paths and records sit correctly behind it."""

from __future__ import annotations

import dataclasses
import importlib
import json
import sys
import time

import httpx
import jwt
import pytest
import respx
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from pydantic import ValidationError
from tc_entra_auth import TokenVerifier

from capital_gateway.config import API_KEY_HEADER, DEMO_BASE_URL, Settings

API = f"{DEMO_BASE_URL}/api/v1"
GATEWAY_KEY = "gateway-caller-key"
TENANT = "11111111-2222-3333-4444-555555555555"
AUDIENCE = "api://tradingcenter-capital-gateway"
TERMINAL_APP = "aaaaaaaa-0000-0000-0000-000000000001"
STRANGER_APP = "bbbbbbbb-0000-0000-0000-000000000002"
EDGE = {"X-TC-Edge": "1"}

SIGNING_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


async def _published_keys() -> dict:
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(SIGNING_KEY.public_key()))
    return {"keys": [{**jwk, "kid": "k1"}]}


def _token(application: str, *, audience: str = AUDIENCE, roles: tuple[str, ...] = ("admin",)) -> str:
    now = int(time.time())
    claims = {
        "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0",
        "aud": audience,
        "exp": now + 600,
        "nbf": now - 5,
        "azp": application,
        "roles": list(roles),
    }
    return jwt.encode(claims, SIGNING_KEY, algorithm="RS256", headers={"kid": "k1"})


def _bearer(application: str, **kwargs) -> dict[str, str]:
    return {**EDGE, "Authorization": f"Bearer {_token(application, **kwargs)}"}


SERVER_ENV = {
    "GATEWAY_ENV": "production",
    "SERVER_MODE": "true",
    "ENTRA_TENANT_ID": TENANT,
    "ENTRA_AUDIENCES": AUDIENCE,
    "BROWSER_CALLER_APPLICATION_IDS": json.dumps([TERMINAL_APP]),
}


@pytest.fixture(autouse=True)
def _credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAPITAL_API_KEY", "super-secret-key")
    monkeypatch.setenv("CAPITAL_IDENTIFIER", "me@example.com")
    monkeypatch.setenv("CAPITAL_PASSWORD", "hunter2")
    monkeypatch.setenv("GATEWAY_API_KEY", GATEWAY_KEY)


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch):
    """The app imported as a server, running its lifespan, with the tenant's keys served from memory."""
    for name, value in SERVER_ENV.items():
        monkeypatch.setenv(name, value)
    importlib.import_module("capital_gateway.app")
    module = importlib.reload(sys.modules["capital_gateway.app"])
    with TestClient(module.app) as client:
        edge = module.app.state.edge
        assert edge is not None
        verifier = TokenVerifier(tenant_id=TENANT, audiences=[AUDIENCE], fetch_keys=_published_keys)
        module.app.state.edge = dataclasses.replace(edge, verifier=verifier)
        yield client
    for name in SERVER_ENV:
        monkeypatch.delenv(name, raising=False)
    importlib.reload(sys.modules["capital_gateway.app"])


def _provider_answers() -> None:
    respx.post(f"{API}/session").mock(
        return_value=httpx.Response(200, headers={"CST": "c", "X-SECURITY-TOKEN": "s"}, json={})
    )
    respx.get(f"{API}/positions").mock(return_value=httpx.Response(200, json={"positions": []}))
    respx.get(f"{API}/session").mock(return_value=httpx.Response(200, json={"accountId": "a1"}))
    respx.get(f"{API}/accounts").mock(return_value=httpx.Response(200, json={"accounts": []}))


@respx.mock
def test_a_browser_token_through_the_edge_reaches_the_account(server: TestClient) -> None:
    _provider_answers()
    assert server.get("/accounts", headers=_bearer(TERMINAL_APP)).status_code == 200


@pytest.mark.parametrize("roles", [("viewer",), ()], ids=["viewer", "no-role"])
@respx.mock
def test_a_person_who_is_not_an_admin_does_not_reach_the_account(server: TestClient, roles) -> None:
    # The terminal's registration hands a token for this audience to any guest of the tenant; the role is what refuses it.
    _provider_answers()
    assert server.get("/accounts", headers=_bearer(TERMINAL_APP, roles=roles)).status_code == 403


@respx.mock
def test_a_browser_token_does_not_reach_a_path_beyond_the_account(server: TestClient) -> None:
    _provider_answers()
    response = server.get("/instruments/US100/terms", headers=_bearer(TERMINAL_APP))
    assert response.status_code == 403


@pytest.mark.parametrize(
    "headers",
    [
        _bearer(STRANGER_APP),
        {**EDGE, "Authorization": "Bearer garbage"},
        _bearer(TERMINAL_APP, audience="api://somebody-else"),
        {**EDGE, API_KEY_HEADER: GATEWAY_KEY},
        EDGE,
    ],
    ids=["unknown-application", "garbage", "wrong-audience", "key-from-outside", "nothing"],
)
@respx.mock
def test_the_edge_without_an_admitted_token_is_refused(server: TestClient, headers: dict) -> None:
    route = respx.get(f"{API}/positions")
    assert server.get("/positions", headers=headers).status_code == 401
    assert route.call_count == 0


@respx.mock
def test_another_service_with_the_key_reaches_every_route(server: TestClient) -> None:
    _provider_answers()
    assert server.get("/positions", headers={API_KEY_HEADER: GATEWAY_KEY}).status_code == 200


def test_another_service_without_the_key_is_refused(server: TestClient) -> None:
    assert server.get("/positions").status_code == 401
    assert server.get("/positions", headers={API_KEY_HEADER: "wrong"}).status_code == 401


def test_the_health_probe_needs_nothing_from_either_side(server: TestClient) -> None:
    assert server.get("/", headers=EDGE).status_code == 200
    assert server.get("/").status_code == 200


def test_the_stream_still_checks_its_own_key_from_either_side(server: TestClient) -> None:
    from starlette.websockets import WebSocketDisconnect

    for headers in (EDGE, {}):
        with pytest.raises(WebSocketDisconnect) as refused, server.websocket_connect(
            "/ws/stream?symbol=US100", headers=headers
        ):
            pass
        assert refused.value.code == 4401
        # With the key it gets past the door and fails on the missing symbol instead.
        with pytest.raises(WebSocketDisconnect) as admitted, server.websocket_connect(
            "/ws/stream", headers={**headers, API_KEY_HEADER: GATEWAY_KEY}
        ):
            pass
        assert admitted.value.code == 1008


def test_a_platform_principal_header_is_not_an_identity(server: TestClient) -> None:
    import base64

    forged = base64.b64encode(json.dumps({"claims": [{"typ": "azp", "val": TERMINAL_APP}]}).encode())
    headers = {"X-MS-CLIENT-PRINCIPAL": forged.decode()}
    assert server.get("/accounts", headers=headers).status_code == 401
    assert server.get("/accounts", headers={**EDGE, **headers}).status_code == 401


def _settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    for name, value in {**SERVER_ENV, **env}.items():
        monkeypatch.setenv(name, value)
    return Settings()  # type: ignore[call-arg]


def test_server_mode_in_the_settings_names_the_internal_caller_a_module(monkeypatch) -> None:
    settings = _settings(monkeypatch)
    assert "tc-internal" in settings.module_caller_application_ids
    assert settings.audiences == [AUDIENCE]


@pytest.mark.parametrize(
    "env",
    [{"GATEWAY_ENV": ""}, {"ENTRA_TENANT_ID": ""}, {"ENTRA_AUDIENCES": " , "}],
    ids=["not-production", "no-tenant", "no-audience"],
)
def test_server_mode_without_what_it_needs_refuses_to_start(monkeypatch, env) -> None:
    with pytest.raises(ValidationError):
        _settings(monkeypatch, **env)
