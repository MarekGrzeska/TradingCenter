"""move-from-azure-to-vps — the workbench behind the edge proxy with no platform authenticator. The token check is
tested in `packages/tc-entra-auth`; here is that this process wires it outermost, in front of its own records, with the
paths Easy Auth used to exclude — and that a server never starts with a door the records would leave open."""

from __future__ import annotations

import dataclasses
import json
import time
from types import SimpleNamespace

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import ValidationError
from starlette.types import Receive, Scope, Send
from tc_entra_auth import EdgeAuth, TokenVerifier

from agent.config import Settings as AgentSettings
from teams.config import Settings as TeamsSettings
from workbench.app import app as workbench_app
from workbench.config import Settings
from workbench.edge import EXEMPT_PATHS, edge_config
from workbench.root_access import RootCallers

TENANT = "11111111-2222-3333-4444-555555555555"
AUDIENCE = "api://tradingcenter-workbench"
TERMINAL = "terminal-app-id"
STRANGER = "somebody-else"
EDGE = {"X-TC-Edge": "1"}
MODEL = {
    "id": "m",
    "model": "m",
    "display_name": "m",
    "cost_rank": 1,
    "input_rate_per_1m": 1,
    "output_rate_per_1m": 1,
}
SIGNING_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


async def _published_keys() -> dict:
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(SIGNING_KEY.public_key()))
    return {"keys": [{**jwk, "kid": "k1"}]}


def _bearer(application: str, roles: tuple[str, ...] = ("admin",)) -> dict[str, str]:
    now = int(time.time())
    claims = {
        "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0",
        "aud": AUDIENCE,
        "exp": now + 600,
        "nbf": now - 5,
        "azp": application,
        "roles": list(roles),
    }
    token = jwt.encode(claims, SIGNING_KEY, algorithm="RS256", headers={"kid": "k1"})
    return {**EDGE, "Authorization": f"Bearer {token}"}


async def _reached(scope: Scope, receive: Receive, send: Send) -> None:
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"reached"})


def _door() -> httpx.AsyncClient:
    """The two layers in the order the assembly puts them: the token check outside, the root record inside it."""
    state = SimpleNamespace(
        settings=SimpleNamespace(
            require_authenticated_principal=True, rest_caller_application_ids=TERMINAL
        )
    )
    inner = RootCallers(_reached, state=state, package_prefixes=frozenset({"/market"}))
    verifier = TokenVerifier(tenant_id=TENANT, audiences=[AUDIENCE], fetch_keys=_published_keys)
    config = dataclasses.replace(
        edge_config(_server_settings()), verifier=verifier  # type: ignore[type-var]
    )
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=EdgeAuth(inner, config)), base_url="http://workbench"
    )


def _server_settings(**overrides) -> Settings:
    values = {
        "agent_database_url": "postgresql://x@127.0.0.1/a",
        "teams_database_url": "postgresql://x@127.0.0.1/t",
        "polymarket_database_url": "postgresql://x@127.0.0.1/p",
        "social_database_url": "postgresql://x@127.0.0.1/s",
        "market_database_url": "postgresql://x@127.0.0.1/m",
        "telegram_database_url": "postgresql://x@127.0.0.1/tg",
        "gateway_api_key": "gateway-key",
        "agent_openai_api_key": "k",
        "teams_openai_api_key": "k",
        "agent_default_model_id": "m",
        "server_mode": True,
        "require_authenticated_principal": True,
        "entra_tenant_id": TENANT,
        "entra_audiences": AUDIENCE,
    }
    return Settings(_env_file=None, **{**values, **overrides})  # type: ignore[call-arg]


async def test_the_terminal_with_a_token_reaches_the_root() -> None:
    async with _door() as client:
        assert (await client.get("/sessions", headers=_bearer(TERMINAL))).status_code == 200


async def test_a_valid_token_of_an_application_nobody_listed_is_refused_by_the_record() -> None:
    async with _door() as client:
        assert (await client.get("/sessions", headers=_bearer(STRANGER))).status_code == 403


@pytest.mark.parametrize("path", ["/sessions", "/market/pairs", "/telegram/bots"])
async def test_the_edge_without_a_token_never_reaches_any_surface(path) -> None:
    async with _door() as client:
        assert (await client.get(path, headers=EDGE)).status_code == 401


@pytest.mark.parametrize("path", sorted(EXEMPT_PATHS))
async def test_the_paths_easy_auth_excluded_need_no_token(path) -> None:
    async with _door() as client:
        assert (await client.get(path, headers=EDGE)).status_code == 200


def test_the_excluded_paths_are_the_ones_infra_excluded() -> None:
    assert EXEMPT_PATHS == {"/health", "/market/ping", "/market/ws/candles"}


async def test_no_key_opens_the_workbench_from_inside_the_network() -> None:
    async with _door() as client:
        assert (await client.get("/sessions", headers={"X-Gateway-Key": "gateway-key"})).status_code == 401


async def test_the_assembled_application_refuses_before_its_settings_exist(monkeypatch) -> None:
    """Nothing is served until the lifespan has filled the state, whatever the path: the outermost layer is the one
    saying so, which is how this proves the assembly installed it. The state is emptied first, because the application
    object is shared and another test's lifespan may already have filled it."""
    monkeypatch.delattr(workbench_app.state, "edge", raising=False)
    transport = httpx.ASGITransport(app=workbench_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://workbench") as client:
        assert (await client.get("/sessions", headers=EDGE)).status_code == 503


def test_a_process_that_is_not_a_server_has_no_edge_config() -> None:
    assert edge_config(_server_settings(server_mode=False)) is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"require_authenticated_principal": False},
        {"entra_tenant_id": " "},
        {"entra_audiences": ""},
    ],
    ids=["records-would-admit-anybody", "no-tenant", "no-audience"],
)
def test_server_mode_without_what_it_needs_refuses_to_start(overrides) -> None:
    with pytest.raises(ValidationError):
        _server_settings(**overrides)


def _agent_settings(**overrides) -> AgentSettings:
    values = {
        "database_url": "postgresql://x@127.0.0.1/a",
        "openai_api_key": "k",
        "models": [MODEL],
        "default_model_id": "m",
        "trading_mcp_url": "http://trading-mcp:80",
        "private_hosts": "trading-mcp",
        "trading_mcp_api_key": "gateway-key",
    }
    return AgentSettings(_env_file=None, **{**values, **overrides})  # type: ignore[call-arg]


def test_a_tool_server_on_a_private_host_is_reached_by_key_alone() -> None:
    assert _agent_settings().trading_mcp_url == "http://trading-mcp:80"


@pytest.mark.parametrize(
    "overrides",
    [
        {"trading_mcp_api_key": None},
        {"trading_mcp_scope": "api://x/.default"},
        {"private_hosts": ""},
    ],
    ids=["no-key", "scope-beside-key", "host-not-private"],
)
def test_a_private_tool_server_is_refused_unless_it_is_exactly_that(overrides) -> None:
    with pytest.raises(ValidationError):
        _agent_settings(**overrides)


def test_the_teams_surface_reads_the_private_host_the_same_way() -> None:
    values = {
        "database_url": "postgresql://x@127.0.0.1/t",
        "openai_api_key": "k",
        "models": [MODEL],
        "trading_mcp_url": "http://trading-mcp:80",
        "private_hosts": "trading-mcp",
        "trading_mcp_api_key": "gateway-key",
    }
    assert TeamsSettings(_env_file=None, **values).trading_mcp_url == "http://trading-mcp:80"  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        TeamsSettings(_env_file=None, **{**values, "trading_mcp_api_key": None})  # type: ignore[call-arg]


@pytest.mark.parametrize("surface", ["agent", "teams"])
async def test_a_tool_server_behind_the_key_is_reached_with_it_and_refuses_another(surface) -> None:
    """The pairing that matters, against a real server wearing trading-mcp's door: the client the conversation (or a
    team) holds presents the gateway's key, and a client configured without it is refused rather than let in."""
    from agent.tools import ToolServer as AgentToolServer
    from teams.tools.client import ToolServer as TeamsToolServer

    from .mcp_stand_in import _build, free_port, serving_app

    port = free_port()
    stand_in = _build(("list_tracked_pairs",), port, None).streamable_http_app()
    guarded = EdgeAuth(stand_in, edge_config_for_tools("gateway-key"))
    url = f"http://127.0.0.1:{port}"
    common = {
        "openai_api_key": "k",
        "models": [MODEL],
        "trading_mcp_url": url,
        "private_hosts": "127.0.0.1",
        "_env_file": None,
    }
    if surface == "agent":
        make = lambda **kw: AgentToolServer(
            AgentSettings(database_url="postgresql://x@127.0.0.1/a", default_model_id="m", **common, **kw)  # type: ignore[arg-type]
        )
    else:
        make = lambda **kw: TeamsToolServer(
            TeamsSettings(database_url="postgresql://x@127.0.0.1/t", **common, **kw)  # type: ignore[arg-type]
        )

    async with serving_app(guarded, port):
        with_key = make(trading_mcp_api_key="gateway-key")
        try:
            assert [tool.name for tool in await with_key.list_tools()] == ["list_tracked_pairs"]
        finally:
            await with_key.aclose()

        wrong_key = make(trading_mcp_api_key="not-the-key")
        try:
            try:
                tools = await wrong_key.list_tools()
            except Exception:  # noqa: BLE001 - the surfaces differ in whether a refusal raises or comes back empty
                tools = []
            assert tools == []
        finally:
            await wrong_key.aclose()


def edge_config_for_tools(key: str):
    """trading-mcp's door as `trading_mcp.server.edge_config` builds it: no verifier, the key, `/health` open."""
    from tc_entra_auth import EdgeConfig

    return EdgeConfig(
        verifier=None,
        service_key=key,
        key_header=b"x-gateway-key",
        exempt_paths=frozenset({"/health"}),
    )


def test_the_door_and_the_in_process_wrapper_agree_on_the_scope_key():
    from tc_entra_auth.edge import IN_PROCESS_SCOPE_KEY
    from tc_runtime.caller_access import IN_PROCESS_CALLER

    assert IN_PROCESS_SCOPE_KEY == IN_PROCESS_CALLER


@pytest.mark.parametrize(("application", "status"), [("operator-mcp-client", None), (TERMINAL, 403), (STRANGER, 403)])
async def test_a_package_tool_surface_answers_from_outside_only_the_listed_client(application, status) -> None:
    """`operator-mcp-access`: the door and a real package's record, in the order the assembly puts them. The terminal's
    token — valid, admin — is not a tool caller."""
    from starlette.applications import Starlette
    from starlette.routing import Mount

    import market_data.app

    package = market_data.app.create_app()
    package.state.settings = SimpleNamespace(
        require_authenticated_principal=True,
        tool_caller_ids=frozenset({"operator-mcp-client"}),
        rest_caller_ids=frozenset({TERMINAL}),
    )
    verifier = TokenVerifier(tenant_id=TENANT, audiences=[AUDIENCE], fetch_keys=_published_keys)
    config = dataclasses.replace(edge_config(_server_settings()), verifier=verifier)  # type: ignore[type-var]
    door = EdgeAuth(Starlette(routes=[Mount("/market", app=package)]), config)
    transport = httpx.ASGITransport(app=door, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://workbench") as client:
        answered = await client.post("/market/mcp", headers=_bearer(application), json={})

    if status is None:
        assert answered.status_code not in (401, 403)
    else:
        assert answered.status_code == status
