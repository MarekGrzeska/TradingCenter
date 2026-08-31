"""run_team, read_run, list_runs — starting work and reading what it did (specs/teams-mcp-tools): a trace a model can
act on, and a partial one that says it is partial."""

from __future__ import annotations

import httpx
import pytest
import respx
from mcp.server.fastmcp.exceptions import ToolError

from .conftest import BASE

pytestmark = pytest.mark.usefixtures("signed_in")


def _run(status="completed", stopped_reason=None):
    return {
        "id": 5,
        "team_revision_id": 9,
        "status": status,
        "stopped_reason": stopped_reason,
        "started_at": "2026-08-17T00:00:00Z",
        "finished_at": "2026-08-17T00:05:00Z" if status == "completed" else None,
        "created_at": "2026-08-17T00:00:00Z",
    }


def _step(step_id=1, agent_key="scout", status="completed", output="the trend is up"):
    return {
        "id": step_id,
        "run_id": 5,
        "agent_key": agent_key,
        "status": status,
        "output": output,
        "rounds": 2,
        "started_at": "2026-08-17T00:00:00Z",
        "finished_at": "2026-08-17T00:01:00Z",
    }


@respx.mock
async def test_run_team_starts_a_run_and_says_it_is_still_working(server) -> None:
    mcp, teams = server
    respx.post(f"{BASE}/teams/1/runs").mock(
        return_value=httpx.Response(201, json=_run(status="pending"))
    )

    _content, structured = await mcp.call_tool("run_team", {"team_id": 1})

    assert structured["run_id"] == 5
    assert "read_run" in structured["note"]
    await teams.aclose()


@respx.mock
async def test_the_daily_cost_limit_refuses_the_run_naming_its_number(server) -> None:
    mcp, teams = server
    respx.post(f"{BASE}/teams/1/runs").mock(
        return_value=httpx.Response(
            422,
            json={"detail": "this team's daily cost limit is used up: 5.10 spent today of 5 allowed. No run was started."},
        )
    )

    with pytest.raises(ToolError) as err:
        await mcp.call_tool("run_team", {"team_id": 1})

    assert "5.10" in str(err.value)
    assert "No run was started" in str(err.value)
    await teams.aclose()


@respx.mock
async def test_read_run_gathers_the_trace_and_the_cost(server) -> None:
    mcp, teams = server
    respx.get(f"{BASE}/runs/5").mock(return_value=httpx.Response(200, json=_run()))
    respx.get(f"{BASE}/runs/5/steps").mock(
        return_value=httpx.Response(200, json=[_step(), _step(2, "judge", output="buy")])
    )
    respx.get(f"{BASE}/runs/5/tool-calls").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"id": 1, "run_step_id": 1, "round_index": 0, "position": 0,
                 "tool_name": "get_candles", "arguments": {}, "outcome": "ok",
                 "result_text": "...", "duration_ms": 12, "created_at": "2026-08-17T00:00:00Z"}
            ],
        )
    )
    respx.get(f"{BASE}/usage").mock(
        return_value=httpx.Response(200, json={"total_cost": "0.42", "by_agent": [], "by_model": []})
    )

    _content, structured = await mcp.call_tool("read_run", {"run_id": 5})

    assert structured["finished"] is True
    assert structured["cost"] == "0.42"
    assert structured["steps"][0]["tool_calls"] == 1
    assert structured["steps"][1]["tool_calls"] == 0
    assert structured["steps"][1]["output"] == "buy"
    await teams.aclose()


@respx.mock
async def test_read_run_says_a_working_run_is_not_finished(server) -> None:
    """A partial trace answered as a result is the one mistake this tool must not make."""
    mcp, teams = server
    respx.get(f"{BASE}/runs/5").mock(return_value=httpx.Response(200, json=_run(status="running")))
    respx.get(f"{BASE}/runs/5/steps").mock(
        return_value=httpx.Response(200, json=[_step(status="running", output=None)])
    )
    respx.get(f"{BASE}/runs/5/tool-calls").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{BASE}/usage").mock(
        return_value=httpx.Response(200, json={"total_cost": "0.10", "by_agent": [], "by_model": []})
    )

    _content, structured = await mcp.call_tool("read_run", {"run_id": 5})

    assert structured["finished"] is False
    assert structured["status"] == "running"
    await teams.aclose()


@respx.mock
async def test_read_run_carries_the_reason_a_run_was_stopped(server) -> None:
    mcp, teams = server
    respx.get(f"{BASE}/runs/5").mock(
        return_value=httpx.Response(
            200, json=_run(status="failed", stopped_reason="the run's cost limit was reached")
        )
    )
    respx.get(f"{BASE}/runs/5/steps").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{BASE}/runs/5/tool-calls").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{BASE}/usage").mock(
        return_value=httpx.Response(200, json={"total_cost": "5.00", "by_agent": [], "by_model": []})
    )

    _content, structured = await mcp.call_tool("read_run", {"run_id": 5})

    assert "cost limit" in structured["stopped_reason"]
    await teams.aclose()


@respx.mock
async def test_a_very_long_output_is_shortened_rather_than_filling_the_turn(server) -> None:
    mcp, teams = server
    respx.get(f"{BASE}/runs/5").mock(return_value=httpx.Response(200, json=_run()))
    respx.get(f"{BASE}/runs/5/steps").mock(
        return_value=httpx.Response(200, json=[_step(output="x" * 5000)])
    )
    respx.get(f"{BASE}/runs/5/tool-calls").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{BASE}/usage").mock(
        return_value=httpx.Response(200, json={"total_cost": "0", "by_agent": [], "by_model": []})
    )

    _content, structured = await mcp.call_tool("read_run", {"run_id": 5})

    output = structured["steps"][0]["output"]
    assert len(output) < 5000
    assert "more characters" in output
    await teams.aclose()


@respx.mock
async def test_list_runs_answers_newest_first_as_teams_ordered_them(server) -> None:
    mcp, teams = server
    respx.get(f"{BASE}/teams/1/runs").mock(
        return_value=httpx.Response(200, json=[_run(), _run(status="failed")])
    )

    _content, structured = await mcp.call_tool("list_runs", {"team_id": 1})

    assert len(structured["result"]) == 2
    assert structured["result"][1]["status"] == "failed"
    await teams.aclose()
