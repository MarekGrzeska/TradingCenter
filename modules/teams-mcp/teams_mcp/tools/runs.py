"""Running a team, and reading what it did.

`read_run` is the tool this whole module is for. Composing a team from a sentence is the
easy half; the expensive half is looking at what came out and changing one prompt because
of it, and that only works if the trace arrives in a shape a model can reason about
(specs/teams-mcp-tools, "Zestaw odpowiada na pytania o to, co się wydarzyło").
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from pydantic import BaseModel

from ..client import TeamsClient
from ._shared import READ_ONLY, WRITE, _call, summarised

# The two statuses that mean the run is still going. Anything else is an end state.
_IN_PROGRESS = ("pending", "running")


class StartedRun(BaseModel):
    run_id: int
    team_revision_id: int
    status: str
    note: str


class RunStep(BaseModel):
    agent_key: str
    status: str
    output: str | None
    rounds: int
    tool_calls: int


class RunDetail(BaseModel):
    run_id: int
    status: str
    finished: bool
    stopped_reason: str | None
    steps: list[RunStep]
    cost: str | None


class RunSummary(BaseModel):
    run_id: int
    status: str
    started_at: str | None
    finished_at: str | None


def register(mcp: FastMCP, teams: TeamsClient) -> None:
    @mcp.tool(annotations=WRITE)
    async def run_team(context: Context, team_id: int) -> StartedRun:
        """Start a run of this team's latest revision. Answers as soon as the run exists,
        not when it finishes — a team takes minutes, so read it back with `read_run`.

        **This spends real money** on the operator's own OpenAI key, once per agent per
        round. It is refused before anything is created when the team has used up its
        daily cost limit, or its daily order limit if it trades; both refusals name the
        number that stopped them. A revision naming a model no longer in the catalogue is
        refused too.
        """
        run = await _call(teams, context, "POST", f"/teams/{team_id}/runs")
        return StartedRun(
            run_id=run["id"],
            team_revision_id=run["team_revision_id"],
            status=run["status"],
            note=(
                "started — it is working now. Read it back with read_run in a minute or "
                "two; nothing is lost if this conversation ends first."
            ),
        )

    @mcp.tool(annotations=READ_ONLY)
    async def read_run(context: Context, run_id: int) -> RunDetail:
        """What a run did: every agent's status and what it answered, how many rounds it
        took, how many tool calls it made, and what the whole run cost.

        Works while the run is still going — `finished` is false and the outputs are
        whatever exists so far. A partial trace is not a result, and answering the
        operator as though it were is the one mistake to avoid here.
        """
        run = await _call(teams, context, "GET", f"/runs/{run_id}")
        steps = await _call(teams, context, "GET", f"/runs/{run_id}/steps")
        calls = await _call(teams, context, "GET", f"/runs/{run_id}/tool-calls")
        usage = await _call(teams, context, "GET", "/usage", params={"run_id": run_id})

        per_step: dict[int, int] = {}
        for call in calls:
            per_step[call["run_step_id"]] = per_step.get(call["run_step_id"], 0) + 1

        return RunDetail(
            run_id=run["id"],
            status=run["status"],
            finished=run["status"] not in _IN_PROGRESS,
            stopped_reason=run["stopped_reason"],
            steps=[
                RunStep(
                    agent_key=step["agent_key"],
                    status=step["status"],
                    output=summarised(step["output"]),
                    rounds=step["rounds"],
                    tool_calls=per_step.get(step["id"], 0),
                )
                for step in steps
            ],
            cost=usage.get("total_cost") if isinstance(usage, dict) else None,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def list_runs(context: Context, team_id: int) -> list[RunSummary]:
        """Every run of this team, newest first — including runs of revisions since
        replaced, which is what makes two of them comparable at all."""
        rows: list[dict[str, Any]] = await _call(teams, context, "GET", f"/teams/{team_id}/runs")
        return [
            RunSummary(
                run_id=row["id"],
                status=row["status"],
                started_at=row["started_at"],
                finished_at=row["finished_at"],
            )
            for row in rows
        ]
