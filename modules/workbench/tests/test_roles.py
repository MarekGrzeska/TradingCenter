"""access-roles — the workbench's use of the role policy: what a viewer may reach through the real edge config, and
that the two archives they read expose nothing on `GET` that writes. The policy itself is tested in `packages/tc-entra-auth`."""

from __future__ import annotations

import dataclasses
import importlib
import pkgutil

import httpx
import pytest
from starlette.types import Receive, Scope, Send
from tc_entra_auth import EdgeAuth, TokenVerifier

from workbench.edge import VIEWER_READ_PREFIXES, edge_config

from . import test_server_mode as server

# Every `GET` the two archives the viewer may read answer today. A new one fails this test until somebody has looked at
# it: a `GET` that writes would be open to every viewer.
READ_ONLY_GETS = {
    "social_data": {"/", "/health", "/ping", "/news", "/news/sources", "/posts", "/posts/{source}/{external_id}", "/state"},
    "polymarket_data": {
        "/",
        "/health",
        "/ping",
        "/groups",
        "/events",
        "/events/{provider_event_id}",
        "/snapshot",
        "/outcomes/{outcome_id}/history",
        "/events/{provider_event_id}/changes",
    },
}


def _gets(package: str) -> set[str]:
    found: set[str] = set()
    for module in pkgutil.iter_modules(importlib.import_module(f"{package}.routers").__path__):
        router = getattr(importlib.import_module(f"{package}.routers.{module.name}"), "router", None)
        for route in getattr(router, "routes", []):
            if "GET" in route.methods:
                found.add(route.path)
    return found


@pytest.mark.parametrize("package", sorted(READ_ONLY_GETS))
def test_every_get_of_an_archive_a_viewer_reads_has_been_read_as_a_read(package) -> None:
    assert _gets(package) == READ_ONLY_GETS[package]


async def _reached(scope: Scope, receive: Receive, send: Send) -> None:
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"reached"})


def _door() -> httpx.AsyncClient:
    config = edge_config(server._server_settings())
    assert config is not None
    verifier = TokenVerifier(tenant_id=server.TENANT, audiences=[server.AUDIENCE], fetch_keys=server._published_keys)
    config = dataclasses.replace(config, verifier=verifier)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=EdgeAuth(_reached, config)), base_url="http://workbench"
    )


@pytest.mark.parametrize(
    ("method", "path", "status"),
    [
        ("GET", "/social/news", 200),
        ("GET", "/polymarket/events", 200),
        ("GET", "/me", 200),
        ("PUT", "/social/news/keep", 403),
        ("DELETE", "/polymarket/events/x", 403),
        ("GET", "/sessions", 403),
        ("POST", "/sessions", 403),
        ("GET", "/teams", 403),
        ("GET", "/market/instruments", 403),
        ("GET", "/telegram/bots", 403),
        ("GET", "/alerts/rules", 403),
        ("GET", "/youtube/videos", 403),
        ("GET", "/strategies/strategies", 403),
        ("POST", "/strategies/runs", 403),
        ("GET", "/social/mcp", 403),
        ("POST", "/polymarket/mcp", 403),
    ],
)
async def test_a_viewer_reaches_the_two_archives_for_reading_and_no_other_door(method, path, status) -> None:
    async with _door() as client:
        response = await client.request(method, path, headers=server._bearer(server.TERMINAL, ("viewer",)))
    assert response.status_code == status


async def test_a_person_with_no_role_reaches_nothing_but_me() -> None:
    async with _door() as client:
        headers = server._bearer(server.TERMINAL, ())
        assert (await client.get("/me", headers=headers)).status_code == 200
        assert (await client.get("/social/news", headers=headers)).status_code == 403


def test_the_viewer_prefixes_are_the_archives_only() -> None:
    assert VIEWER_READ_PREFIXES == ("/social", "/polymarket")


async def test_me_says_what_the_door_wrote_and_admin_where_there_is_no_door() -> None:
    from starlette.requests import Request

    from workbench.app import me

    def request(*headers: tuple[bytes, bytes]) -> Request:
        return Request({"type": "http", "headers": list(headers)})

    seen = await me(request((b"x-tc-roles", b"viewer"), (b"x-ms-client-principal-id", b"person-1")))
    assert (seen.roles, seen.person) == (["viewer"], "person-1")
    assert (await me(request((b"x-tc-roles", b"")))).roles == []
    assert (await me(request())).roles == ["admin"]
