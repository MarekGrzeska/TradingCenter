"""The record that says which caller may reach which surface, and every way it refuses.

The tests matter more here than the code does: this layer is the only thing standing
between a caller admitted for eleven read-only tools and `DELETE /pairs/{symbol}`. Before
the tools moved in, `agent` and `teams` had neither an address for this module nor a
credential for it, and the prohibition held by construction. It holds by this file now.
"""

from __future__ import annotations

import base64
import inspect
import json
import types

import httpx
import pytest
from starlette.middleware.base import BaseHTTPMiddleware

from market_data.caller_access import (
    OPEN_PATHS,
    REST_PATHS,
    CallerAccess,
    Surface,
    calling_application,
    surface_for,
)
from market_data.config import Settings

AGENT = "agent-application-id"
TEAMS = "teams-application-id"
TERMINAL = "terminal-application-id"
STRANGER = "some-other-application-id"


def _settings(require: bool = True) -> Settings:
    return Settings(
        database_url="postgresql://localhost:5432/test?sslmode=require",
        database_user="test-user",
        gateway_api_key="test-gateway-key",
        require_authenticated_principal=require,
        tool_caller_application_ids=f"{AGENT}, {TEAMS}",
        rest_caller_application_ids=TERMINAL,
        _env_file=None,
    )


def _wrap(require: bool = True):
    """The layer around a sentinel that records having been reached.

    A sentinel rather than the real application: what is under test is the decision, and
    a real route would need a database to prove it was allowed to run.
    """
    reached: list[str] = []

    async def sentinel(scope, receive, send):
        reached.append(scope.get("path", ""))
        response = httpx.Response(200, json={"reached": True})
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": response.content})

    state = types.SimpleNamespace(settings=_settings(require))
    return CallerAccess(sentinel, state=state), reached


def _client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://archive.test"
    )


def _as(application: str | None, person: str = "a-person-object-id") -> dict[str, str]:
    """The headers Easy Auth puts on a request it let through.

    Both of them, and the pair is the whole lesson of 19 August 2026: the claims blob names
    the **application** the token was issued to, while `X-MS-CLIENT-PRINCIPAL-ID` names the
    person for a delegated token. The record is written in applications, so a test that
    only set the id header was testing a header this module must not decide on.
    """
    if application is None:
        return {}
    return {
        "X-MS-CLIENT-PRINCIPAL": _principal_blob(application),
        "X-MS-CLIENT-PRINCIPAL-ID": person,
    }


def _principal_blob(application: str, claim: str = "azp") -> str:
    """Easy Auth's own encoding: base64 of `{"auth_typ": …, "claims": [{"typ", "val"}, …]}`."""
    blob = {
        "auth_typ": "aad",
        "name_typ": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name",
        "role_typ": "http://schemas.microsoft.com/ws/2008/06/identity/claims/role",
        "claims": [
            {"typ": "aud", "val": "api://tradingcenter-market-data"},
            {"typ": "iss", "val": "https://login.microsoftonline.com/tenant/v2.0"},
            {"typ": "oid", "val": "a-person-object-id"},
            {"typ": claim, "val": application},
        ],
    }
    return base64.b64encode(json.dumps(blob).encode("utf-8")).decode("ascii")


# --- 4.1: the form, which is as load-bearing as the rule ---


def test_the_layer_is_raw_asgi_not_a_starlette_base_middleware() -> None:
    """`BaseHTTPMiddleware` buffers a response body in some Starlette versions, which
    would break the streamable-http transport `/mcp` is served over. The same check
    `tc-mcp-kit` keeps on its own middleware, for the same reason."""
    assert not issubclass(CallerAccess, BaseHTTPMiddleware)
    assert CallerAccess.__mro__ == (CallerAccess, object)
    # The three-argument ASGI signature, which is what "raw" means here: a scope, and the
    # two callables. `BaseHTTPMiddleware` would hand a `Request` to a `dispatch` instead.
    assert list(inspect.signature(CallerAccess.__call__).parameters) == [
        "self",
        "scope",
        "receive",
        "send",
    ]
    assert "BaseHTTPMiddleware" not in inspect.getsource(CallerAccess)


# --- 4.2: the record's two lists, read from settings ---


def test_the_caller_lists_are_parsed_from_one_setting_each() -> None:
    settings = _settings()
    assert settings.tool_caller_ids == {AGENT, TEAMS}
    assert settings.rest_caller_ids == {TERMINAL}


def test_blank_and_absent_lists_are_empty_rather_than_a_caller_named_nothing() -> None:
    settings = Settings(
        database_url="postgresql://localhost:5432/test?sslmode=require",
        database_user="test-user",
        gateway_api_key="test-gateway-key",
        tool_caller_application_ids=" , ",
        _env_file=None,
    )
    assert settings.tool_caller_ids == frozenset()
    assert settings.rest_caller_ids == frozenset()


# --- 4.4: every "identity — surface it has no right to" pair ---


TOOL_CALLER_MUST_NOT_REACH = [
    ("POST", "/pairs"),
    ("DELETE", "/pairs/US100"),
    ("GET", "/candles/US100"),
    ("POST", "/stream-tickets"),
    ("POST", "/jobs/estimate"),
    ("DELETE", "/jobs/7"),
    ("GET", "/pairs"),
    ("GET", "/openapi.json"),
]


@pytest.mark.parametrize("method,path", TOOL_CALLER_MUST_NOT_REACH)
@pytest.mark.parametrize("caller", [AGENT, TEAMS])
async def test_a_tool_caller_is_refused_every_rest_route(
    method: str, path: str, caller: str
) -> None:
    """The two writing routes are the reason this layer exists, and the reading ones are
    here too: the rule is "this caller has no business on REST", not "not on the
    dangerous half of REST"."""
    layer, reached = _wrap()

    async with _client(layer) as client:
        response = await client.request(method, path, headers=_as(caller))

    assert response.status_code == 403
    assert reached == []


@pytest.mark.parametrize("path", ["/mcp", "/mcp/", "/mcp/messages"])
async def test_a_rest_caller_is_refused_the_tool_surface(path: str) -> None:
    layer, reached = _wrap()

    async with _client(layer) as client:
        response = await client.post(path, headers=_as(TERMINAL))

    assert response.status_code == 403
    assert reached == []


@pytest.mark.parametrize("caller", [AGENT, TEAMS])
async def test_a_tool_caller_reaches_the_tool_surface(caller: str) -> None:
    layer, reached = _wrap()

    async with _client(layer) as client:
        response = await client.post("/mcp", headers=_as(caller))

    assert response.status_code == 200
    assert reached == ["/mcp"]


async def test_the_rest_caller_reaches_the_rest_contract() -> None:
    layer, reached = _wrap()

    async with _client(layer) as client:
        response = await client.get("/candles/US100", headers=_as(TERMINAL))

    assert response.status_code == 200
    assert reached == ["/candles/US100"]


async def test_an_identity_on_neither_list_is_refused_rather_than_trusted() -> None:
    """It got past Easy Auth, which means the platform authenticated it. That is the
    question this layer does not ask."""
    layer, reached = _wrap()

    async with _client(layer) as client:
        tools = await client.post("/mcp", headers=_as(STRANGER))
        rest = await client.get("/pairs", headers=_as(STRANGER))

    assert tools.status_code == 403
    assert rest.status_code == 403
    assert reached == []


async def test_no_identity_at_all_is_refused_where_the_requirement_is_on() -> None:
    layer, reached = _wrap()

    async with _client(layer) as client:
        response = await client.get("/pairs")

    assert response.status_code == 401
    assert response.json() == {"detail": "not authenticated"}
    assert reached == []


async def test_local_work_needs_no_identity_and_no_list() -> None:
    """Nothing stands in front of a local process, so there is no identity to have. The
    lists are read only where the requirement is on, which is why they are empty in a
    developer's `.env` rather than filled with placeholders."""
    layer, reached = _wrap(require=False)

    async with _client(layer) as client:
        tools = await client.post("/mcp")
        rest = await client.get("/pairs")

    assert tools.status_code == 200
    assert rest.status_code == 200
    assert reached == ["/mcp", "/pairs"]


# --- 4.5: a path the record does not name ---


@pytest.mark.parametrize("path", ["/admin", "/candles/US100/forming/extra", "/pairs/US100/rows"])
@pytest.mark.parametrize("caller", [AGENT, TERMINAL])
async def test_a_path_outside_the_record_is_refused_not_passed(path: str, caller: str) -> None:
    """The default is the point. Passing an unrecorded path would mean a REST route added
    next month is reachable by the agent on the day it is written."""
    layer, reached = _wrap()

    async with _client(layer) as client:
        response = await client.get(path, headers=_as(caller))

    assert response.status_code == 403
    assert reached == []


def test_every_published_route_is_in_the_record() -> None:
    """The other half of refusing by default: a route nobody classified would be
    unreachable, which is a failure this test names at the moment it is added rather than
    at the moment somebody notices the terminal cannot read it."""
    from market_data.app import create_app

    published = set(create_app().openapi()["paths"])
    unclassified = {path for path in published if surface_for(path.replace("{", "").replace("}", "")) is None}
    assert unclassified == set()


# --- 4.3 and 4.6: the paths open with no identity, and the assertion that freezes them ---


def test_the_open_paths_are_exactly_these_two() -> None:
    """Equality, not membership, and that is the whole test: any path added here fails
    CI, so a data-carrying route cannot be exempted from identity quietly. `/ping` answers
    a constant and `/ws/candles` cannot carry a header — each has its reason written
    beside it in `caller_access.py`, and a third entry needs one too."""
    assert OPEN_PATHS == {"/ping", "/ws/candles"}


@pytest.mark.parametrize("path", sorted(OPEN_PATHS))
async def test_an_open_path_needs_no_identity(path: str) -> None:
    layer, reached = _wrap()

    async with _client(layer) as client:
        response = await client.get(path)

    assert response.status_code == 200
    assert reached == [path]


async def test_a_websocket_to_the_stream_is_let_through() -> None:
    layer, _reached = _wrap()
    sent: list[dict] = []

    async def send(message):
        sent.append(message)

    async def receive():  # pragma: no cover - the sentinel never reads
        return {"type": "websocket.connect"}

    await layer({"type": "websocket", "path": "/ws/candles", "headers": []}, receive, send)

    assert [message["type"] for message in sent] == ["http.response.start", "http.response.body"]


async def test_a_websocket_anywhere_else_is_closed_rather_than_passed() -> None:
    """`RequireCallerIdentity` passes every `websocket` scope through — free for a module
    with no WebSockets, a hole in one that has them (design.md, D4)."""
    layer, reached = _wrap()
    sent: list[dict] = []

    async def send(message):
        sent.append(message)

    async def receive():  # pragma: no cover
        return {"type": "websocket.connect"}

    await layer({"type": "websocket", "path": "/ws/anything", "headers": []}, receive, send)

    assert sent == [
        {
            "type": "websocket.close",
            "code": 1008,
            "reason": "this path is not open to any caller",
        }
    ]
    assert reached == []


def test_the_rest_record_does_not_reach_into_the_tool_surface() -> None:
    assert surface_for("/mcp") is Surface.TOOLS
    assert surface_for("/mcp/messages") is Surface.TOOLS
    assert all(not path.startswith("/mcp") for path in REST_PATHS)


async def test_missing_settings_refuse_rather_than_allow() -> None:
    """A process whose lifespan has not filled the state is not yet serving, so this is
    not a state a running instance reaches. Refused anyway: "the settings were not there"
    must never be the reading under which every route is open."""
    reached: list[str] = []

    async def sentinel(scope, receive, send):  # pragma: no cover - must not be reached
        reached.append(scope.get("path", ""))

    layer = CallerAccess(sentinel, state=types.SimpleNamespace())

    async with _client(layer) as client:
        response = await client.get("/pairs", headers=_as(TERMINAL))

    assert response.status_code == 503
    assert reached == []


async def test_an_open_path_answers_before_the_settings_exist() -> None:
    """Which is why `/ping` is checked before them: the platform's probe reaches a
    container whose lifespan is still applying a migration, and a 503 there reads as a
    dead process (`deploy_probe.py`)."""
    reached: list[str] = []

    async def sentinel(scope, receive, send):
        reached.append(scope.get("path", ""))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    layer = CallerAccess(sentinel, state=types.SimpleNamespace())

    async with _client(layer) as client:
        response = await client.get("/ping")

    assert response.status_code == 200
    assert reached == ["/ping"]


# --- the identity itself: which fact the record is written in --------------------------


async def test_a_person_in_the_id_header_is_not_the_caller() -> None:
    """The production failure of 19 August 2026, as a test.

    The terminal presents a **delegated** token, and Easy Auth fills
    `X-MS-CLIENT-PRINCIPAL-ID` with the signed-in person's object id — not the terminal
    application's. A record of application identifiers can never match that, so every REST
    request was refused until the image was rolled back. What must not happen again is this
    module deciding on that header at all: without a claims blob there is no calling
    application to name, and no identifier here is one either.
    """
    layer, reached = _wrap()

    async with _client(layer) as client:
        response = await client.get(
            "/pairs", headers={"X-MS-CLIENT-PRINCIPAL-ID": "e6b7d7ba-a-person-not-an-app"}
        )

    assert response.status_code == 401
    assert reached == []


@pytest.mark.parametrize("claim", ["azp", "appid", "http://schemas.microsoft.com/identity/claims/appid"])
def test_the_calling_application_is_read_from_any_spelling_of_the_claim(claim: str) -> None:
    """`azp` in a v2 token, `appid` in a v1 one, and Easy Auth passes some claim types
    through in their long URI form. Three spellings, one fact."""
    headers = {b"x-ms-client-principal": _principal_blob(TERMINAL, claim=claim).encode()}

    assert calling_application(headers) == TERMINAL


def test_a_blob_that_will_not_decode_names_nobody() -> None:
    """And naming nobody is a refusal upstream, never a pass."""
    assert calling_application({b"x-ms-client-principal": b"not base64 at all !!"}) is None
    assert calling_application({b"x-ms-client-principal": base64.b64encode(b"{]")}) is None
    assert calling_application({}) is None


def test_a_blob_carrying_only_a_person_names_nobody() -> None:
    """`oid` and `sub` name the person at the keyboard. This module admits programs."""
    blob = base64.b64encode(
        json.dumps({"claims": [{"typ": "oid", "val": "a-person"}]}).encode()
    )

    assert calling_application({b"x-ms-client-principal": blob}) is None


async def test_the_terminals_delegated_token_reaches_rest() -> None:
    """The whole point of the fix: the person varies, the application does not."""
    layer, reached = _wrap()

    async with _client(layer) as client:
        first = await client.get("/pairs", headers=_as(TERMINAL, person="operator-one"))
        second = await client.get("/pairs", headers=_as(TERMINAL, person="operator-two"))

    assert (first.status_code, second.status_code) == (200, 200)
    assert reached == ["/pairs", "/pairs"]


async def test_a_tool_callers_own_token_still_only_reaches_the_tools() -> None:
    """A client-credentials token has no person in it at all — the claim this module reads
    is the same one either way."""
    layer, reached = _wrap()
    headers = {"X-MS-CLIENT-PRINCIPAL": _principal_blob(AGENT)}

    async with _client(layer) as client:
        tools = await client.post("/mcp", headers=headers)
        rest = await client.delete("/pairs/US100", headers=headers)

    assert (tools.status_code, rest.status_code) == (200, 403)
    assert reached == ["/mcp"]
