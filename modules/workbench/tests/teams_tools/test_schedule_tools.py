"""The schedule tools: creating, listing, pausing, editing and deleting.

`unattended_ack` used to be the point of this file — a parameter deliberately absent, so
that a model could not fill in a safeguard the moment a refusal was in its way. The
safeguard is gone (`manage-schedules-and-drop-the-acknowledgement`), so what is held here
now is the other half of the same worry: that a model reaching for the destructive tool
gets a different tool from the reversible one, and that editing does not go through
delete-and-recreate.
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
        "created_at": "2026-08-17T00:00:00Z",
        "updated_at": "2026-08-17T00:00:00Z",
        **overrides,
    }


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


# --- managing what is already there ---------------------------------------------------


async def test_the_published_set_covers_the_whole_life_of_a_schedule(server) -> None:
    """Creating without managing is the shape this change was opened over: the operator
    sets a schedule with a sentence and is sent to the terminal for every change after."""
    mcp, teams = server
    names = {tool.name for tool in await mcp.list_tools()}

    assert {
        "schedule_team",
        "trigger_team",
        "list_schedules",
        "pause_schedule",
        "pause_trigger",
        "edit_schedule",
        "edit_trigger",
        "delete_schedule",
        "delete_trigger",
    } <= names
    await teams.aclose()


async def test_only_the_two_deleting_tools_are_marked_destructive(server) -> None:
    """A client that asks before a destructive call has nothing but the annotation to go
    on, and `delete_schedule` must not look like `schedule_team` to it."""
    mcp, teams = server
    destructive = {
        tool.name
        for tool in await mcp.list_tools()
        if tool.annotations and tool.annotations.destructiveHint
    }

    assert destructive == {"delete_schedule", "delete_trigger"}
    await teams.aclose()


@respx.mock
async def test_pausing_disables_and_resuming_enables(server) -> None:
    mcp, teams = server
    paused = respx.post(f"{BASE}/schedules/11/disable").mock(
        return_value=httpx.Response(200, json=_schedule(enabled=False))
    )
    resumed = respx.post(f"{BASE}/schedules/11/enable").mock(
        return_value=httpx.Response(200, json=_schedule(enabled=True))
    )

    _content, off = await mcp.call_tool("pause_schedule", {"schedule_id": 11})
    _content, on = await mcp.call_tool("pause_schedule", {"schedule_id": 11, "resume": True})

    assert paused.called and resumed.called
    assert "paused" in off["result"]
    assert "enabled" in on["result"]
    await teams.aclose()


@respx.mock
async def test_editing_a_schedule_keeps_the_row_it_edits(server) -> None:
    """The whole reason `edit_schedule` exists rather than delete-and-recreate: the
    identifier and the history are what the operator is talking about."""
    mcp, teams = server
    respx.get(f"{BASE}/schedules/11").mock(return_value=httpx.Response(200, json=_schedule()))
    saved = respx.put(f"{BASE}/schedules/11").mock(
        return_value=httpx.Response(200, json=_schedule(cron_expression="35 * * * 1,2,3,4,5"))
    )
    deleted = respx.delete(f"{BASE}/schedules/11").mock(return_value=httpx.Response(204))

    _content, structured = await mcp.call_tool(
        "edit_schedule", {"schedule_id": 11, "cron_expression": "35 * * * 1,2,3,4,5"}
    )

    body = json.loads(saved.calls.last.request.read())
    assert body["cron_expression"] == "35 * * * 1,2,3,4,5"
    # The revision the schedule already ran stays put when none is named.
    assert body["pinned_revision_id"] == 9
    assert structured["schedule_id"] == 11
    assert not deleted.called
    await teams.aclose()


@respx.mock
async def test_editing_a_trigger_changes_only_what_was_named(server) -> None:
    mcp, teams = server
    respx.get(f"{BASE}/triggers/21").mock(return_value=httpx.Response(200, json=_trigger()))
    saved = respx.put(f"{BASE}/triggers/21").mock(
        return_value=httpx.Response(200, json=_trigger(threshold="80.00000000"))
    )

    await mcp.call_tool("edit_trigger", {"trigger_id": 21, "threshold": "80"})

    body = json.loads(saved.calls.last.request.read())
    assert body["threshold"] == "80"
    assert body["field_path"] == "rsi"
    assert body["comparison"] == "gt"
    assert body["cooldown_seconds"] == 900
    await teams.aclose()


@respx.mock
async def test_a_zero_cooldown_travels_instead_of_being_swallowed(server) -> None:
    """`cooldown_seconds=0` is falsy, and `or` read that as "not given" — so the tool kept
    the old value and answered with a success naming it. The operator asked for something
    and was told it had been done.

    Whether zero is *allowed* is teams' question, not this module's: it refuses a
    non-positive cooldown with a sentence (`contract.py`, `_positive`). Forwarding the
    value is what lets that refusal reach whoever asked, instead of a silent no-op.
    """
    mcp, teams = server
    respx.get(f"{BASE}/triggers/21").mock(return_value=httpx.Response(200, json=_trigger()))
    saved = respx.put(f"{BASE}/triggers/21").mock(
        return_value=httpx.Response(200, json=_trigger())
    )

    await mcp.call_tool("edit_trigger", {"trigger_id": 21, "cooldown_seconds": 0})

    body = json.loads(saved.calls.last.request.read())
    assert body["cooldown_seconds"] == 0, "the old 900 would mean the request never left"
    await teams.aclose()


@respx.mock
async def test_a_zero_poll_interval_travels_too(server) -> None:
    """Same shape, same `or`, one field over."""
    mcp, teams = server
    respx.get(f"{BASE}/triggers/21").mock(return_value=httpx.Response(200, json=_trigger()))
    saved = respx.put(f"{BASE}/triggers/21").mock(
        return_value=httpx.Response(200, json=_trigger())
    )

    await mcp.call_tool("edit_trigger", {"trigger_id": 21, "poll_interval_seconds": 0})

    body = json.loads(saved.calls.last.request.read())
    assert body["poll_interval_seconds"] == 0
    await teams.aclose()


@respx.mock
async def test_deleting_says_what_it_took_and_what_it_left(server) -> None:
    mcp, teams = server
    removed = respx.delete(f"{BASE}/schedules/11").mock(return_value=httpx.Response(204))

    _content, structured = await mcp.call_tool("delete_schedule", {"schedule_id": 11})

    assert removed.called
    said = structured["result"]
    assert "fire history" in said
    assert "runs it started are untouched" in said
    await teams.aclose()


@respx.mock
async def test_deleting_a_schedule_that_is_not_there_refuses_rather_than_pretending(
    server,
) -> None:
    mcp, teams = server
    respx.delete(f"{BASE}/schedules/11").mock(return_value=httpx.Response(404))

    with pytest.raises(ToolError) as err:
        await mcp.call_tool("delete_schedule", {"schedule_id": 11})

    assert "nothing at" in str(err.value)
    await teams.aclose()
