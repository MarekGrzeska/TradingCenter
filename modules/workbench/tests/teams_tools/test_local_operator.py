"""The boundary the refusal has: what a tool does when no operator identity arrives, on a
machine where none could have.

Its own file because every other tool test supplies one through `signed_in`
(`conftest.py`) — the whole point here is calling without one, and a module-level fixture
that hands one over would leave nothing tested.

The condition used to have two halves, and lost one with the merge: "an authenticator in
front **or** a remote teams". There is no remote teams. What is left is the flag, and the
two tests that turned on the address are gone with it.
"""

from __future__ import annotations

import logging

import httpx
import pytest
import respx
from mcp.server.fastmcp.exceptions import ToolError

from teams_tools.server import say_whose_name_the_tools_act_in

from .conftest import BASE

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
async def test_a_read_with_nobody_behind_it_carries_no_identity(server) -> None:
    mcp, teams = server
    route = respx.get(f"{BASE}/teams").mock(return_value=httpx.Response(200, json=[_TEAM]))

    _content, structured = await mcp.call_tool("list_teams", {})

    assert structured["result"][0]["name"] == "morning desk"
    assert "x-ms-client-principal-id" not in route.calls.last.request.headers
    await teams.aclose()


@respx.mock
async def test_a_write_with_nobody_behind_it_goes_the_same_way(server) -> None:
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
    assert "x-ms-client-principal-id" not in created.calls.last.request.headers
    await teams.aclose()


@respx.mock
async def test_the_same_call_is_refused_where_an_identity_could_have_existed(
    guarded_server,
) -> None:
    mcp, teams = guarded_server
    route = respx.get(f"{BASE}/teams").mock(return_value=httpx.Response(200, json=[]))

    with pytest.raises(ToolError) as err:
        await mcp.call_tool("list_teams", {})

    assert "no operator identity" in str(err.value)
    # Refused before anything is called, not after: the refusal exists so that nothing is
    # read or written, and a request that went out would already have been read.
    assert not route.called
    await teams.aclose()


@respx.mock
async def test_a_write_is_refused_there_too_and_reaches_nothing(guarded_server) -> None:
    mcp, teams = guarded_server
    route = respx.post(f"{BASE}/teams").mock(return_value=httpx.Response(201, json=_TEAM))

    with pytest.raises(ToolError) as err:
        await mcp.call_tool(
            "create_team",
            {"name": "morning desk", "agents": [_AGENT], "limits": {"daily_limit": "5"}},
        )

    assert "no operator identity" in str(err.value)
    assert not route.called
    await teams.aclose()


async def test_no_tool_takes_an_identity_as_an_argument_in_any_shape(server) -> None:
    """"Tożsamość operatora jest przenoszona, a nie odgadywana" — a field a model can fill
    is a field a model can borrow, so the argument is not ignored at runtime: it does not
    exist. Checked against the published schemas rather than the source, because the schema
    is what a model actually sees."""
    mcp, teams = server
    forbidden = ("owner", "principal", "operator", "token", "authorization", "identity")

    for tool in await mcp.list_tools():
        properties = (tool.inputSchema or {}).get("properties", {})
        for name in properties:
            assert not any(word in name.lower() for word in forbidden), (
                f"{tool.name} takes {name!r}, which a model could fill with somebody else's"
            )

    await teams.aclose()


def test_the_process_says_at_startup_that_tools_act_without_an_identity(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="teams_tools.server"):
        say_whose_name_the_tools_act_in(True)

    said = caplog.text
    assert "REQUIRE_AUTHENTICATED_PRINCIPAL=false" in said
    assert "no identity" in said


def test_it_says_the_other_state_when_an_operator_is_required(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="teams_tools.server"):
        say_whose_name_the_tools_act_in(False)

    said = caplog.text
    assert "refused" in said
    assert "carrying no identity" not in said
