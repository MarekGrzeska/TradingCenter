"""list_teams, read_team, create_team, revise_team — the catalogue half of the surface.

specs/teams-mcp-tools: one call per thing the operator asked for, and a correction that
names only what changes.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from mcp.server.fastmcp.exceptions import ToolError

from .conftest import BASE, OPERATOR

pytestmark = pytest.mark.usefixtures("signed_in")

_AGENT = {
    "key": "scout",
    "role": "scout",
    "prompt": "read the market",
    "guidance": "",
    "model_id": "gpt-5.6-luna",
    "tools": [],
}
_JUDGE = {**_AGENT, "key": "judge", "role": "judge", "prompt": "decide"}


def _revision(agents=None, edges=None, version=1, revision_id=9):
    return {
        "id": revision_id,
        "team_id": 1,
        "version": version,
        "definition": {
            "agents": agents if agents is not None else [_AGENT],
            "edges": edges or [],
            "limits": {"run_limit": None, "daily_limit": "5"},
            "trading": {},
        },
        "created_at": "2026-08-17T00:00:00Z",
    }


@respx.mock
async def test_list_teams_answers_the_operators_own_catalogue(server) -> None:
    mcp, teams = server
    respx.get(f"{BASE}/teams").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": 1,
                    "name": "morning desk",
                    "description": "",
                    "latest_revision": 3,
                    "created_at": "2026-08-17T00:00:00Z",
                    "updated_at": "2026-08-17T00:00:00Z",
                }
            ],
        )
    )

    _content, structured = await mcp.call_tool("list_teams", {})

    assert structured["result"][0]["name"] == "morning desk"
    await teams.aclose()


@respx.mock
async def test_create_team_saves_a_team_and_its_first_revision_in_one_call(server) -> None:
    mcp, teams = server
    created = respx.post(f"{BASE}/teams").mock(
        return_value=httpx.Response(
            201,
            json={
                "id": 1,
                "name": "morning desk",
                "description": "",
                "latest_revision": 1,
                "created_at": "2026-08-17T00:00:00Z",
                "updated_at": "2026-08-17T00:00:00Z",
            },
        )
    )
    respx.get(f"{BASE}/teams/1/revisions/latest").mock(
        return_value=httpx.Response(200, json=_revision())
    )

    _content, structured = await mcp.call_tool(
        "create_team",
        {"name": "morning desk", "agents": [_AGENT], "limits": {"daily_limit": "5"}},
    )

    assert structured["team_id"] == 1
    assert structured["agents"] == ["scout"]
    body = created.calls.last.request.read().decode()
    assert "morning desk" in body
    assert "daily_limit" in body
    await teams.aclose()


@respx.mock
async def test_create_team_carries_the_operators_token(server) -> None:
    mcp, teams = server
    created = respx.post(f"{BASE}/teams").mock(
        return_value=httpx.Response(
            201,
            json={
                "id": 1,
                "name": "d",
                "description": "",
                "latest_revision": 1,
                "created_at": "2026-08-17T00:00:00Z",
                "updated_at": "2026-08-17T00:00:00Z",
            },
        )
    )
    respx.get(f"{BASE}/teams/1/revisions/latest").mock(
        return_value=httpx.Response(200, json=_revision())
    )

    await mcp.call_tool("create_team", {"name": "d", "agents": [_AGENT]})

    assert created.calls.last.request.headers["x-ms-client-principal-id"] == OPERATOR
    await teams.aclose()


@respx.mock
async def test_create_team_refusal_names_the_agent_teams_named(server) -> None:
    mcp, teams = server
    respx.post(f"{BASE}/teams").mock(
        return_value=httpx.Response(
            422, json={"detail": "agent 'scout' names model 'gpt-9', which is not in the catalogue"}
        )
    )

    with pytest.raises(ToolError) as err:
        await mcp.call_tool("create_team", {"name": "d", "agents": [_AGENT]})

    assert "scout" in str(err.value)
    assert "gpt-9" in str(err.value)
    await teams.aclose()


@respx.mock
async def test_revise_team_replaces_one_role_and_keeps_the_rest(server) -> None:
    mcp, teams = server
    respx.get(f"{BASE}/teams/1/revisions/latest").mock(
        return_value=httpx.Response(200, json=_revision(agents=[_AGENT, _JUDGE]))
    )
    saved = respx.post(f"{BASE}/teams/1/revisions").mock(
        return_value=httpx.Response(
            201,
            json=_revision(
                agents=[{**_AGENT, "prompt": "read the market carefully"}, _JUDGE],
                version=2,
                revision_id=10,
            ),
        )
    )

    _content, structured = await mcp.call_tool(
        "revise_team",
        {
            "team_id": 1,
            "replace_agents": [{**_AGENT, "prompt": "read the market carefully"}],
        },
    )

    body = saved.calls.last.request.read().decode()
    # The role that was not named survives, and the one that was is the new text.
    assert "judge" in body
    assert "read the market carefully" in body
    assert structured["version"] == 2
    assert structured["agents"] == ["scout", "judge"]
    await teams.aclose()


@respx.mock
async def test_revise_team_keeps_limits_that_were_not_named(server) -> None:
    mcp, teams = server
    respx.get(f"{BASE}/teams/1/revisions/latest").mock(
        return_value=httpx.Response(200, json=_revision())
    )
    saved = respx.post(f"{BASE}/teams/1/revisions").mock(
        return_value=httpx.Response(201, json=_revision(version=2))
    )

    await mcp.call_tool(
        "revise_team", {"team_id": 1, "replace_agents": [{**_AGENT, "prompt": "new"}]}
    )

    # The daily limit was never mentioned in the patch and must not be dropped by it —
    # a correction that silently removes the cost ceiling is the expensive kind of bug.
    body = json.loads(saved.calls.last.request.read())
    assert body["definition"]["limits"]["daily_limit"] == "5"
    await teams.aclose()


@respx.mock
async def test_revise_team_adds_an_agent_whose_key_is_new(server) -> None:
    mcp, teams = server
    respx.get(f"{BASE}/teams/1/revisions/latest").mock(
        return_value=httpx.Response(200, json=_revision())
    )
    saved = respx.post(f"{BASE}/teams/1/revisions").mock(
        return_value=httpx.Response(201, json=_revision(agents=[_AGENT, _JUDGE], version=2))
    )

    await mcp.call_tool("revise_team", {"team_id": 1, "replace_agents": [_JUDGE]})

    body = saved.calls.last.request.read().decode()
    assert "scout" in body and "judge" in body
    await teams.aclose()


@respx.mock
async def test_revise_team_removing_an_agent_that_is_not_there_writes_nothing(server) -> None:
    mcp, teams = server
    respx.get(f"{BASE}/teams/1/revisions/latest").mock(
        return_value=httpx.Response(200, json=_revision())
    )
    saved = respx.post(f"{BASE}/teams/1/revisions").mock(return_value=httpx.Response(201))

    with pytest.raises(ToolError) as err:
        await mcp.call_tool("revise_team", {"team_id": 1, "remove_agent_keys": ["nobody"]})

    assert "nobody" in str(err.value)
    assert not saved.called
    await teams.aclose()


@respx.mock
async def test_revise_team_with_nothing_to_change_is_refused_before_reading(server) -> None:
    mcp, teams = server
    read = respx.get(f"{BASE}/teams/1/revisions/latest").mock(return_value=httpx.Response(200))

    with pytest.raises(ToolError):
        await mcp.call_tool("revise_team", {"team_id": 1})

    assert not read.called
    await teams.aclose()


@respx.mock
async def test_read_team_answers_the_definition_a_correction_needs(server) -> None:
    mcp, teams = server
    respx.get(f"{BASE}/teams/1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 1,
                "name": "morning desk",
                "description": "reads the open",
                "latest_revision": 1,
                "created_at": "2026-08-17T00:00:00Z",
                "updated_at": "2026-08-17T00:00:00Z",
            },
        )
    )
    respx.get(f"{BASE}/teams/1/revisions/latest").mock(
        return_value=httpx.Response(200, json=_revision())
    )

    _content, structured = await mcp.call_tool("read_team", {"team_id": 1})

    assert structured["revision_id"] == 9
    assert structured["agents"][0]["key"] == "scout"
    assert structured["limits"]["daily_limit"] == "5"
    await teams.aclose()


@respx.mock
async def test_somebody_elses_team_reads_as_one_that_does_not_exist(server) -> None:
    mcp, teams = server
    respx.get(f"{BASE}/teams/7").mock(return_value=httpx.Response(404))

    with pytest.raises(ToolError) as err:
        await mcp.call_tool("read_team", {"team_id": 7})

    assert "somebody else" in str(err.value)
    await teams.aclose()


@respx.mock
async def test_a_created_team_is_reported_as_created_even_if_reading_it_back_fails(
    server,
) -> None:
    """The team exists the moment teams answers the POST. If the follow-up read fails and
    this tool reports a failure, the model creates the team again — the exact duplicate
    the no-retry rule exists to prevent, committed by the tool rather than the client."""
    mcp, teams = server
    created = respx.post(f"{BASE}/teams").mock(
        return_value=httpx.Response(
            201,
            json={
                "id": 4,
                "name": "desk",
                "description": "",
                "latest_revision": 1,
                "created_at": "2026-08-17T00:00:00Z",
                "updated_at": "2026-08-17T00:00:00Z",
            },
        )
    )
    respx.get(f"{BASE}/teams/4/revisions/latest").mock(return_value=httpx.Response(503))

    _content, structured = await mcp.call_tool("create_team", {"name": "desk", "agents": [_AGENT]})

    assert created.call_count == 1
    assert structured["team_id"] == 4
    assert structured["revision_id"] is None
    assert "Do not create it again" in structured["note"]
    assert structured["agents"] == ["scout"]
    await teams.aclose()
