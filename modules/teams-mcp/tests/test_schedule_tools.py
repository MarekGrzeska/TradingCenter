"""schedule_team, trigger_team, list_schedules — and the argument that is deliberately
absent.

design.md D4: `unattended_ack` is not a parameter and must never become one. A safeguard
offered to a model as a fillable field is a safeguard that gets filled in the moment a
refusal is in the way.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from mcp.server.fastmcp.exceptions import ToolError

from .conftest import BASE

pytestmark = pytest.mark.usefixtures("signed_in")

_REVISION = {
    "id": 9,
    "team_id": 1,
    "version": 1,
    "definition": {"agents": [], "edges": [], "limits": {}, "trading": {}},
    "created_at": "2026-08-17T00:00:00Z",
}


def _schedule(**overrides):
    return {
        "id": 11,
        "team_id": 1,
        "revision_mode": "pinned",
        "pinned_revision_id": 9,
        "cron_expression": "0 7 * * 1-5",
        "next_fire_at": "2026-08-18T07:00:00Z",
        "enabled": True,
        "disabled_reason": None,
        "consecutive_failures": 0,
        "unattended_ack": False,
        "created_at": "2026-08-17T00:00:00Z",
        "updated_at": "2026-08-17T00:00:00Z",
        **overrides,
    }


def _trigger(**overrides):
    return {
        "id": 21,
        "team_id": 1,
        "revision_mode": "pinned",
        "pinned_revision_id": 9,
        "tool_name": "read_indicators",
        "arguments": {"symbol": "US100"},
        "field_path": "rsi",
        "comparison": "gt",
        "threshold": "70.00000000",
        "cooldown_seconds": 900,
        "poll_interval_seconds": 300,
        "next_check_at": "2026-08-17T00:05:00Z",
        "last_result": None,
        "last_checked_at": None,
        "last_fired_at": None,
        "enabled": True,
        "disabled_reason": None,
        "consecutive_failures": 0,
        "unattended_ack": False,
        "created_at": "2026-08-17T00:00:00Z",
        "updated_at": "2026-08-17T00:00:00Z",
        **overrides,
    }


@respx.mock
async def test_schedule_team_never_sends_an_acknowledgement(server) -> None:
    mcp, teams = server
    respx.get(f"{BASE}/teams/1/revisions/latest").mock(
        return_value=httpx.Response(200, json=_REVISION)
    )
    saved = respx.post(f"{BASE}/teams/1/schedules").mock(
        return_value=httpx.Response(201, json=_schedule())
    )

    await mcp.call_tool("schedule_team", {"team_id": 1, "cron_expression": "0 7 * * 1-5"})

    body = json.loads(saved.calls.last.request.read())
    assert "unattended_ack" not in body
    await teams.aclose()


async def test_the_schedule_tools_publish_no_acknowledgement_parameter(server) -> None:
    mcp, teams = server
    published = {tool.name: tool.inputSchema for tool in await mcp.list_tools()}

    for name in ("schedule_team", "trigger_team"):
        assert "unattended_ack" not in json.dumps(published[name])
    await teams.aclose()


@respx.mock
async def test_schedule_team_pins_the_current_revision_by_default(server) -> None:
    mcp, teams = server
    respx.get(f"{BASE}/teams/1/revisions/latest").mock(
        return_value=httpx.Response(200, json=_REVISION)
    )
    saved = respx.post(f"{BASE}/teams/1/schedules").mock(
        return_value=httpx.Response(201, json=_schedule())
    )

    _content, structured = await mcp.call_tool(
        "schedule_team", {"team_id": 1, "cron_expression": "0 7 * * 1-5"}
    )

    body = json.loads(saved.calls.last.request.read())
    assert body["revision_mode"] == "pinned"
    assert body["pinned_revision_id"] == 9
    assert structured["schedule_id"] == 11
    await teams.aclose()


@respx.mock
async def test_saving_a_schedule_warns_that_the_clock_may_be_off(server) -> None:
    """The module cannot see teams' SCHEDULER_ENABLED, so it warns every time rather than
    staying quiet — over-warning is wrong about precision, silence is wrong about fact."""
    mcp, teams = server
    respx.get(f"{BASE}/teams/1/revisions/latest").mock(
        return_value=httpx.Response(200, json=_REVISION)
    )
    respx.post(f"{BASE}/teams/1/schedules").mock(
        return_value=httpx.Response(201, json=_schedule())
    )

    _content, structured = await mcp.call_tool(
        "schedule_team", {"team_id": 1, "cron_expression": "0 7 * * 1-5"}
    )

    assert "SCHEDULER_ENABLED" in structured["note"]
    await teams.aclose()


@respx.mock
async def test_an_unattended_write_tool_refusal_reaches_the_model_unedited(server) -> None:
    mcp, teams = server
    respx.get(f"{BASE}/teams/1/revisions/latest").mock(
        return_value=httpx.Response(200, json=_REVISION)
    )
    respx.post(f"{BASE}/teams/1/schedules").mock(
        return_value=httpx.Response(
            422,
            json={"detail": "agent 'trader' carries tool(s) ['place_order'] that this module cannot confirm are read-only"},
        )
    )

    with pytest.raises(ToolError) as err:
        await mcp.call_tool("schedule_team", {"team_id": 1, "cron_expression": "0 7 * * *"})

    assert "trader" in str(err.value)
    assert "place_order" in str(err.value)
    await teams.aclose()


@respx.mock
async def test_an_invalid_cron_expression_is_refused_by_teams_own_words(server) -> None:
    mcp, teams = server
    respx.get(f"{BASE}/teams/1/revisions/latest").mock(
        return_value=httpx.Response(200, json=_REVISION)
    )
    respx.post(f"{BASE}/teams/1/schedules").mock(
        return_value=httpx.Response(
            422, json={"detail": "'every morning' is not a valid five-field cron expression"}
        )
    )

    with pytest.raises(ToolError) as err:
        await mcp.call_tool("schedule_team", {"team_id": 1, "cron_expression": "every morning"})

    assert "five-field cron" in str(err.value)
    await teams.aclose()


@respx.mock
async def test_trigger_team_sends_the_condition_teams_expects(server) -> None:
    mcp, teams = server
    respx.get(f"{BASE}/teams/1/revisions/latest").mock(
        return_value=httpx.Response(200, json=_REVISION)
    )
    saved = respx.post(f"{BASE}/teams/1/triggers").mock(
        return_value=httpx.Response(201, json=_trigger())
    )

    _content, structured = await mcp.call_tool(
        "trigger_team",
        {
            "team_id": 1,
            "tool_name": "read_indicators",
            "field_path": "rsi",
            "comparison": "gt",
            "threshold": "70",
            "arguments": {"symbol": "US100"},
        },
    )

    body = json.loads(saved.calls.last.request.read())
    assert body["tool_name"] == "read_indicators"
    assert body["arguments"] == {"symbol": "US100"}
    assert "unattended_ack" not in body
    assert structured["trigger_id"] == 21
    await teams.aclose()


@respx.mock
async def test_list_schedules_shows_fires_that_started_nothing_and_why(server) -> None:
    mcp, teams = server
    respx.get(f"{BASE}/teams/1/schedules").mock(
        return_value=httpx.Response(200, json=[_schedule(enabled=False, disabled_reason="3 kolejne przebiegi zakończone niepowodzeniem")])
    )
    respx.get(f"{BASE}/teams/1/triggers").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{BASE}/schedules/11/fires").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": 1,
                    "schedule_id": 11,
                    "trigger_id": None,
                    "fired_at": "2026-08-17T07:00:00Z",
                    "outcome": "skipped",
                    "reason": "this team's daily cost limit is used up",
                    "run_id": None,
                    "skipped_count": 0,
                }
            ],
        )
    )

    _content, structured = await mcp.call_tool("list_schedules", {"team_id": 1})

    row = structured["result"][0]
    assert row["enabled"] is False
    assert "niepowodzeniem" in row["disabled_reason"]
    assert row["recent_fires"][0]["outcome"] == "skipped"
    assert "daily cost limit" in row["recent_fires"][0]["reason"]
    await teams.aclose()
