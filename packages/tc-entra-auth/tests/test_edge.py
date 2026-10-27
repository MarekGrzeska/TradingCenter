import base64
import json

import httpx
import pytest
from conftest import AUDIENCE, TENANT
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, WebSocketRoute

from tc_entra_auth import EdgeAuth, EdgeConfig, TokenVerifier, application_in
from tc_entra_auth.edge import principal_blob

KEY = "shared-service-key"
EDGE = {"X-TC-Edge": "1"}


async def whoami(request: Request) -> JSONResponse:
    blob = request.headers.get("x-ms-client-principal")
    application = None
    if blob:
        claims = json.loads(base64.b64decode(blob))["claims"]
        application = claims[0]["val"]
    return JSONResponse(
        {
            "application": application,
            "person": request.headers.get("x-ms-client-principal-id"),
            "name": request.headers.get("x-ms-client-principal-name"),
        }
    )


async def candles(websocket) -> None:
    await websocket.accept()
    await websocket.send_text("hello")
    await websocket.close()


def forged_principal(application: str = "module-app-id") -> str:
    document = {"claims": [{"typ": "azp", "val": application}]}
    return base64.b64encode(json.dumps(document).encode()).decode()


def client(tenant, *, verifier=True) -> httpx.AsyncClient:
    inner = Starlette(
        routes=[
            Route("/whoami", whoami),
            Route("/health", whoami),
            Route("/stream-key", whoami),
            WebSocketRoute("/ws/candles", candles),
        ]
    )
    guarded = EdgeAuth(
        inner,
        EdgeConfig(
            verifier=TokenVerifier(tenant_id=TENANT, audiences=[AUDIENCE], fetch_keys=tenant.jwks)
            if verifier
            else None,
            service_key=KEY,
            exempt_paths=frozenset({"/health", "/ws/candles"}),
            key_paths=frozenset({"/stream-key"}),
        ),
    )
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=guarded), base_url="http://t")


async def test_the_edge_with_a_valid_token_names_the_application(tenant):
    async with client(tenant) as http:
        response = await http.get(
            "/whoami", headers={**EDGE, "Authorization": f"Bearer {tenant.token()}"}
        )
    assert response.status_code == 200
    assert response.json() == {
        "application": "terminal-app-id",
        "person": "person-object-id",
        "name": "operator@example.test",
    }


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer garbage"},
        {"Authorization": "Basic abc"},
        {"X-Gateway-Key": KEY},
    ],
    ids=["nothing", "garbage-token", "wrong-scheme", "key-alone-from-outside"],
)
async def test_the_edge_without_a_valid_token_is_refused(tenant, headers):
    async with client(tenant) as http:
        response = await http.get("/whoami", headers={**EDGE, **headers})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_a_forged_principal_from_outside_is_not_an_identity(tenant):
    forged = {"X-MS-CLIENT-PRINCIPAL": forged_principal(), "X-MS-CLIENT-PRINCIPAL-ID": "x"}
    async with client(tenant) as http:
        response = await http.get("/whoami", headers={**EDGE, **forged})
        assert response.status_code == 401
        # With a valid token, what the record sees is the token's application, never the forged one.
        valid = {"Authorization": f"Bearer {tenant.token()}"}
        response = await http.get("/whoami", headers={**EDGE, **forged, **valid})
    assert response.json()["application"] == "terminal-app-id"


async def test_an_internal_call_with_the_key_is_the_internal_application(tenant):
    async with client(tenant) as http:
        response = await http.get("/whoami", headers={"X-Gateway-Key": KEY})
    assert response.json()["application"] == "tc-internal"


@pytest.mark.parametrize("headers", [{}, {"X-Gateway-Key": "wrong"}, {"X-Gateway-Key": ""}])
async def test_an_internal_call_without_the_key_is_refused(tenant, headers):
    async with client(tenant) as http:
        response = await http.get("/whoami", headers=headers)
    assert response.status_code == 401


async def test_an_internal_call_cannot_pretend_with_a_forged_principal(tenant):
    async with client(tenant) as http:
        response = await http.get("/whoami", headers={"X-MS-CLIENT-PRINCIPAL": forged_principal()})
    assert response.status_code == 401


async def test_a_non_ascii_key_is_a_refusal_not_a_crash(tenant):
    async with client(tenant) as http:
        response = await http.get("/whoami", headers={"X-Gateway-Key": "zażółć".encode()})
    assert response.status_code == 401


async def test_an_exempt_path_needs_no_proof_and_still_loses_forged_identity(tenant):
    async with client(tenant) as http:
        response = await http.get("/health", headers={**EDGE, "X-MS-CLIENT-PRINCIPAL-ID": "forged"})
    assert response.status_code == 200
    assert response.json() == {"application": None, "person": None, "name": None}


async def test_a_key_path_passes_from_both_sides_for_its_handler_to_check(tenant):
    async with client(tenant) as http:
        outside = await http.get("/stream-key", headers=EDGE)
        inside = await http.get("/stream-key")
    assert outside.status_code == inside.status_code == 200


async def test_a_process_with_no_verifier_refuses_everything_from_the_edge(tenant):
    async with client(tenant, verifier=False) as http:
        token = {"Authorization": f"Bearer {tenant.token()}"}
        outside = await http.get("/whoami", headers={**EDGE, **token})
        inside = await http.get("/whoami", headers={"X-Gateway-Key": KEY})
    assert outside.status_code == 401
    assert inside.status_code == 200


async def test_a_process_with_no_key_refuses_every_internal_call():
    inner = Starlette(routes=[Route("/whoami", whoami)])
    guarded = EdgeAuth(inner, EdgeConfig(verifier=None, service_key=None))
    transport = httpx.ASGITransport(app=guarded)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as http:
        response = await http.get("/whoami", headers={"X-Gateway-Key": ""})
    assert response.status_code == 401


async def handshake(app, path: str) -> list[dict]:
    sent: list[dict] = []
    events = iter([{"type": "websocket.connect"}])

    async def receive():
        return next(events, {"type": "websocket.disconnect", "code": 1000})

    async def send(message):
        sent.append(message)

    scope = {
        "type": "websocket",
        "path": path,
        "headers": [(b"x-tc-edge", b"1")],
        "subprotocols": [],
        "query_string": b"",
    }
    await app(scope, receive, send)
    return sent


async def test_a_handshake_is_refused_before_accept_unless_its_path_is_exempt():
    inner = Starlette(
        routes=[WebSocketRoute("/ws/other", candles), WebSocketRoute("/ws/candles", candles)]
    )
    config = EdgeConfig(verifier=None, service_key=KEY, exempt_paths=frozenset({"/ws/candles"}))
    guarded = EdgeAuth(inner, config)

    refused = await handshake(guarded, "/ws/other")
    assert refused[0]["type"] == "websocket.close" and refused[0]["code"] == 1008
    admitted = await handshake(guarded, "/ws/candles")
    assert admitted[0]["type"] == "websocket.accept"


async def test_a_process_that_is_not_a_server_leaves_the_request_alone():
    inner = Starlette(routes=[Route("/whoami", whoami)])
    transport = httpx.ASGITransport(app=EdgeAuth(inner, None))
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as http:
        response = await http.get("/whoami", headers={"X-MS-CLIENT-PRINCIPAL-ID": "from-platform"})
    assert response.json()["person"] == "from-platform"


async def test_a_request_before_the_settings_exist_is_refused_not_waved_through():
    def not_yet() -> EdgeConfig | None:
        raise LookupError("settings")

    inner = Starlette(routes=[Route("/whoami", whoami)])
    transport = httpx.ASGITransport(app=EdgeAuth(inner, not_yet))
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as http:
        response = await http.get("/whoami", headers={"X-Gateway-Key": KEY})
    assert response.status_code == 503


async def test_a_request_this_process_makes_to_itself_keeps_the_operator_it_carries(tenant):
    from tc_entra_auth.edge import IN_PROCESS_SCOPE_KEY

    guarded = client(tenant)._transport.app  # type: ignore[attr-defined]

    async def as_this_process(scope, receive, send):
        await guarded({**scope, IN_PROCESS_SCOPE_KEY: "a test"}, receive, send)

    transport = httpx.ASGITransport(app=as_this_process)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as http:
        response = await http.get("/whoami", headers={"X-MS-CLIENT-PRINCIPAL-ID": "the-operator"})
    assert response.status_code == 200
    assert response.json()["person"] == "the-operator"


async def test_the_in_process_marker_in_a_header_is_not_a_credential(tenant):
    async with client(tenant) as http:
        response = await http.get("/whoami", headers={"tc_runtime.in_process_caller": "x"})
    assert response.status_code == 401


def listed_client(tenant, applications: frozenset[str] | None) -> httpx.AsyncClient:
    guarded = EdgeAuth(
        Starlette(routes=[Route("/whoami", whoami)]),
        EdgeConfig(
            verifier=TokenVerifier(tenant_id=TENANT, audiences=[AUDIENCE], fetch_keys=tenant.jwks),
            service_key=KEY,
            token_applications=applications,
        ),
    )
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=guarded), base_url="http://t")


@pytest.mark.parametrize(
    ("applications", "status"),
    [
        (frozenset({"claude-code-app-id"}), 200),
        (frozenset({"terminal-app-id"}), 403),
        (frozenset(), 403),
        (None, 200),
    ],
)
async def test_a_token_is_admitted_only_from_a_listed_application(tenant, applications, status):
    token = tenant.token(application="claude-code-app-id")
    async with listed_client(tenant, applications) as http:
        response = await http.get("/whoami", headers={**EDGE, "Authorization": f"Bearer {token}"})
    assert response.status_code == status


async def test_the_application_list_does_not_bind_a_service_with_the_key(tenant):
    async with listed_client(tenant, frozenset()) as http:
        response = await http.get("/whoami", headers={"X-Gateway-Key": KEY})
    assert response.status_code == 200
    assert response.json()["application"] == "tc-internal"


@pytest.mark.parametrize(
    ("blob", "application"),
    [(principal_blob("app-1"), "app-1"), (None, None), (b"not base64!", None), (base64.b64encode(b"[]"), None)],
)
def test_what_the_door_wrote_reads_back_and_nothing_else_does(blob, application):
    assert application_in(blob) == application
