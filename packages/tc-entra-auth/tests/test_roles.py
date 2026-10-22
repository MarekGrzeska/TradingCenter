import httpx
import pytest
from conftest import AUDIENCE, TENANT
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from tc_entra_auth import EdgeAuth, EdgeConfig, RolePolicy, TokenVerifier, roles_from_header

KEY = "shared-service-key"
EDGE = {"X-TC-Edge": "1"}
POLICY = RolePolicy(viewer_read_prefixes=("/social", "/polymarket"))


async def echo(request: Request) -> JSONResponse:
    roles = roles_from_header({k.encode(): v.encode() for k, v in request.headers.items()})
    return JSONResponse({"roles": sorted(roles)})


def client(tenant, *, policy: RolePolicy | None = POLICY) -> httpx.AsyncClient:
    methods = ["GET", "POST", "PUT", "DELETE"]
    inner = Starlette(
        routes=[
            Route(path, echo, methods=methods)
            for path in ("/me", "/social/posts", "/social/news/keep", "/polymarket/events/1", "/agent/sessions", "/polymarket/mcp", "/health")
        ]
    )
    guarded = EdgeAuth(
        inner,
        EdgeConfig(
            verifier=TokenVerifier(tenant_id=TENANT, audiences=[AUDIENCE], fetch_keys=tenant.jwks),
            service_key=KEY,
            exempt_paths=frozenset({"/health"}),
            role_policy=policy,
        ),
    )
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=guarded), base_url="http://t")


def bearer(tenant, roles=None, **claims) -> dict[str, str]:
    extra = {"roles": roles} if roles is not None else {}
    return {**EDGE, "Authorization": f"Bearer {tenant.token(extra={**extra, **claims})}"}


async def call(tenant, method, path, headers, policy=POLICY):
    async with client(tenant, policy=policy) as http:
        return await http.request(method, path, headers=headers)


async def test_the_roles_the_process_sees_are_the_tokens_not_the_clients(tenant):
    headers = {**bearer(tenant, ["viewer"]), "X-TC-Roles": "admin"}
    response = await call(tenant, "GET", "/me", headers)
    assert response.json() == {"roles": ["viewer"]}


async def test_a_client_header_does_not_survive_on_a_path_without_proof(tenant):
    response = await call(tenant, "GET", "/health", {"X-TC-Roles": "admin"})
    assert response.json() == {"roles": []}


@pytest.mark.parametrize("claim", [None, [], "admin", ["owner"], {"admin": True}])
async def test_no_usable_role_is_refused_everywhere_but_me(tenant, claim):
    headers = bearer(tenant, claim)
    assert (await call(tenant, "GET", "/social/posts", headers)).status_code == 403
    assert (await call(tenant, "GET", "/agent/sessions", headers)).status_code == 403
    me = await call(tenant, "GET", "/me", headers)
    assert me.status_code == 200
    assert "admin" not in me.json()["roles"] and "viewer" not in me.json()["roles"]


async def test_an_admin_reaches_everything(tenant):
    headers = bearer(tenant, ["admin"])
    for method, path in [("POST", "/agent/sessions"), ("PUT", "/social/news/keep"), ("DELETE", "/polymarket/events/1")]:
        assert (await call(tenant, method, path, headers)).status_code == 200


@pytest.mark.parametrize(
    ("method", "path", "status"),
    [
        ("GET", "/social/posts", 200),
        ("GET", "/polymarket/events/1", 200),
        ("GET", "/me", 200),
        ("PUT", "/social/news/keep", 403),
        ("DELETE", "/polymarket/events/1", 403),
        ("GET", "/agent/sessions", 403),
        ("POST", "/agent/sessions", 403),
        ("GET", "/socialite", 403),
        ("GET", "/polymarket/mcp", 403),
    ],
)
async def test_a_viewer_reads_the_archive_and_nothing_else(tenant, method, path, status):
    response = await call(tenant, method, path, bearer(tenant, ["viewer"]))
    assert response.status_code == status


async def test_a_service_key_is_internal_and_not_held_to_the_viewer_policy(tenant):
    response = await call(tenant, "POST", "/agent/sessions", {"X-Gateway-Key": KEY})
    assert response.status_code == 200
    assert response.json() == {"roles": ["internal"]}


async def test_without_a_policy_the_token_alone_decides(tenant):
    response = await call(tenant, "GET", "/agent/sessions", bearer(tenant), policy=None)
    assert response.status_code == 200
