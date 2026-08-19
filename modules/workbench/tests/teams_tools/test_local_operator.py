"""specs/teams-mcp-authorship, the boundary the refusal now has: what a tool does when no
operator identity arrives, on a machine where none could have.

Its own file because every other tool test supplies a token through `signed_in`
(`conftest.py`) — the whole point here is calling without one, and a module-level fixture
that hands one over would leave nothing tested.
"""

from __future__ import annotations

import logging

import httpx
import pytest
import respx
from mcp.server.fastmcp.exceptions import ToolError
from starlette.testclient import TestClient

from teams_mcp.client import TeamsClient
from teams_mcp.config import Settings
from teams_mcp.server import build_http_app, build_server

from .conftest import BASE, REMOTE

_AGENT = {
    "key": "scout",
    "role": "scout",
    "prompt": "read the market",
    "guidance": "",
    "model_id": "gpt-5.6-luna",
    "tools": [],
}

_TEAM = {
    "id": 1,
    "name": "morning desk",
    "description": "",
    "latest_revision": 1,
    "created_at": "2026-08-17T00:00:00Z",
    "updated_at": "2026-08-17T00:00:00Z",
}

_REVISION = {
    "id": 9,
    "team_id": 1,
    "version": 1,
    "definition": {
        "agents": [_AGENT],
        "edges": [],
        "limits": {"run_limit": None, "daily_limit": "5"},
        "trading": {},
    },
    "created_at": "2026-08-17T00:00:00Z",
}


@respx.mock
async def test_a_read_with_nobody_behind_it_reaches_teams_carrying_no_identity(server) -> None:
    mcp, teams = server
    route = respx.get(f"{BASE}/teams").mock(return_value=httpx.Response(200, json=[_TEAM]))

    _content, structured = await mcp.call_tool("list_teams", {})

    assert structured["result"][0]["name"] == "morning desk"
    assert "authorization" not in route.calls.last.request.headers
    await teams.aclose()


@respx.mock
async def test_a_write_with_nobody_behind_it_reaches_teams_the_same_way(server) -> None:
    """The half that matters: a write is what the requirement used to stop outright, and
    what an operator on a desk actually wants from the chat."""
    mcp, teams = server
    created = respx.post(f"{BASE}/teams").mock(return_value=httpx.Response(201, json=_TEAM))
    respx.get(f"{BASE}/teams/1/revisions/latest").mock(
        return_value=httpx.Response(200, json=_REVISION)
    )

    await mcp.call_tool(
        "create_team",
        {"name": "morning desk", "agents": [_AGENT], "limits": {"daily_limit": "5"}},
    )

    assert created.called
    assert "authorization" not in created.calls.last.request.headers
    await teams.aclose()


@respx.mock
async def test_the_same_call_is_refused_where_an_identity_could_have_existed(
    guarded_server,
) -> None:
    mcp, teams = guarded_server
    route = respx.get(f"{REMOTE}/teams").mock(return_value=httpx.Response(200, json=[]))

    with pytest.raises(ToolError) as err:
        await mcp.call_tool("list_teams", {})

    assert "no operator identity" in str(err.value)
    # Refused before the network, not after: the refusal exists so that nothing is read or
    # written, and a request that went out would already have been read.
    assert not route.called
    await teams.aclose()


@respx.mock
async def test_a_write_is_refused_there_too_and_never_reaches_teams(guarded_server) -> None:
    mcp, teams = guarded_server
    route = respx.post(f"{REMOTE}/teams").mock(return_value=httpx.Response(201, json=_TEAM))

    with pytest.raises(ToolError) as err:
        await mcp.call_tool(
            "create_team",
            {"name": "morning desk", "agents": [_AGENT], "limits": {"daily_limit": "5"}},
        )

    assert "no operator identity" in str(err.value)
    assert not route.called
    await teams.aclose()


@respx.mock
async def test_a_remote_teams_refuses_even_with_no_authenticator_in_front() -> None:
    """The half `Settings.operator_identity_optional` exists for: the flag off, but `teams`
    off this machine. The reason names the missing identity, not the address — what is
    missing is the identity; the address only says one could have existed."""
    settings = Settings(
        teams_url=REMOTE,
        teams_scope="api://tradingcenter-teams/.default",
        require_authenticated_principal=False,
        _env_file=None,  # type: ignore[call-arg]
    )
    client = TeamsClient(settings)
    mcp = build_server(settings, client)
    route = respx.get(f"{REMOTE}/teams").mock(return_value=httpx.Response(200, json=[]))

    with pytest.raises(ToolError) as err:
        await mcp.call_tool("list_teams", {})

    assert "no operator identity" in str(err.value)
    assert "azurewebsites" not in str(err.value)
    assert not route.called
    await client.aclose()


async def test_no_tool_takes_an_identity_as_an_argument_in_any_shape(server) -> None:
    """specs/teams-mcp-authorship, "Tożsamość operatora jest przenoszona, a nie odgadywana"
    — a field a model can fill is a field a model can borrow, so the argument is not
    ignored at runtime: it does not exist. Checked against the published schemas rather
    than the source, because the schema is what a model actually sees."""
    mcp, teams = server
    forbidden = ("owner", "principal", "operator", "token", "authorization", "identity")

    for tool in await mcp.list_tools():
        properties = (tool.inputSchema or {}).get("properties", {})
        for name in properties:
            assert not any(word in name.lower() for word in forbidden), (
                f"{tool.name} takes {name!r}, which a model could fill with somebody else's"
            )

    await teams.aclose()


def _app(*, require: bool, url: str = BASE, scope: str | None = None) -> TestClient:
    settings = Settings(
        teams_url=url,
        teams_scope=scope,
        require_authenticated_principal=require,
        _env_file=None,  # type: ignore[call-arg]
    )
    return TestClient(build_http_app(settings, TeamsClient(settings)))


def test_the_module_says_at_startup_that_tools_act_without_an_identity(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="teams_mcp.server"):
        _app(require=False)

    said = caplog.text
    assert "REQUIRE_AUTHENTICATED_PRINCIPAL=false" in said
    assert BASE in said
    assert "no identity" in said


def test_the_module_says_the_other_state_when_an_operator_is_required(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="teams_mcp.server"):
        _app(require=True, url=REMOTE, scope="api://tradingcenter-teams/.default")

    said = caplog.text
    assert "refused" in said
    assert "carrying no identity" not in said
