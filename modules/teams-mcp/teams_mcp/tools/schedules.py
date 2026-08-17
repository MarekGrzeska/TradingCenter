"""Putting a team on a clock, or on a market condition — and the one argument this
module refuses to let a model fill in.

`unattended_ack` is not a parameter here and will not become one. `teams` refuses a
schedule over a revision carrying a tool it cannot confirm is a read, unless that
acknowledgement is present; offering it as a field means a model sets it the moment a
refusal is in its way, and the safeguard stops existing without a line of code changing
(design.md, D4). The operator ticks that box in the terminal, where they can see what
they are agreeing to.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from mcp.server.fastmcp import Context, FastMCP
from pydantic import BaseModel, Field

from ..client import TeamsClient
from ._shared import READ_ONLY, WRITE, _call

# Said on every schedule and trigger this module creates. It over-warns on purpose: the
# clock's own setting is teams' and is not published on its wire, so this module cannot
# tell a running clock from a stopped one. Warning always is wrong-but-safe; staying
# quiet would be wrong-and-silent, which is the failure specs/teams-mcp-tools is about.
_CLOCK_CAVEAT = (
    "Saved. Note that teams' clock can be switched off entirely (SCHEDULER_ENABLED), and "
    "it is off in production until the operator has watched one fire by hand — while it "
    "is off, nothing here triggers and no history rows appear. This module cannot see "
    "that setting, so ask the operator if the schedule seems silent."
)


class SavedSchedule(BaseModel):
    schedule_id: int
    cron_expression: str
    next_fire_at: str
    enabled: bool
    note: str


class SavedTrigger(BaseModel):
    trigger_id: int
    tool_name: str
    field_path: str
    comparison: str
    threshold: str
    enabled: bool
    note: str


class ScheduleSummary(BaseModel):
    kind: Literal["schedule", "trigger"]
    id: int
    describes: str
    enabled: bool
    disabled_reason: str | None
    recent_fires: list[dict[str, Any]]


def register(mcp: FastMCP, teams: TeamsClient) -> None:
    @mcp.tool(annotations=WRITE)
    async def schedule_team(
        context: Context,
        team_id: int,
        cron_expression: str = Field(
            description=(
                "five-field cron, read as a wall clock in Poland (Europe/Warsaw) — for "
                "example '0 7 * * 1-5' for 07:00 on weekdays, the same 07:00 in summer "
                "and in winter"
            )
        ),
        pinned_revision_id: int | None = None,
    ) -> SavedSchedule:
        """Run this team on a clock, unattended.

        Times are Polish wall-clock times, always — teams rolls the expression forward in
        `Europe/Warsaw`, so 07:00 stays 07:00 across a clock change, and the moment it
        answers with (`next_fire_at`) is that same moment in UTC. By default the schedule
        is **pinned** to the revision
        given (or the current one), so editing the team later does not silently change
        what the robot does at seven in the morning; pass `pinned_revision_id` from
        `read_team` to pin an older one deliberately.

        Refused, naming the agent and the tool, if the revision carries a tool teams
        cannot confirm is read-only — a team that can place orders needs the operator's
        own acknowledgement, ticked in the terminal. That is not something this
        conversation can agree to on their behalf.
        """
        if pinned_revision_id is None:
            revision = await _call(teams, context, "GET", f"/teams/{team_id}/revisions/latest")
            pinned_revision_id = revision["id"]

        body = {
            "revision_mode": "pinned",
            "pinned_revision_id": pinned_revision_id,
            "cron_expression": cron_expression,
        }
        saved = await _call(teams, context, "POST", f"/teams/{team_id}/schedules", json=body)
        return SavedSchedule(
            schedule_id=saved["id"],
            cron_expression=saved["cron_expression"],
            next_fire_at=saved["next_fire_at"],
            enabled=saved["enabled"],
            note=_CLOCK_CAVEAT,
        )

    @mcp.tool(annotations=WRITE)
    async def trigger_team(
        context: Context,
        team_id: int,
        tool_name: str,
        field_path: str,
        comparison: Literal["gt", "gte", "lt", "lte", "eq"],
        threshold: str,
        arguments: dict[str, Any] | None = None,
        cooldown_seconds: int = 900,
        poll_interval_seconds: int = 300,
        pinned_revision_id: int | None = None,
    ) -> SavedTrigger:
        """Run this team when a market condition becomes true.

        The condition is one call to a tool teams already has — `tool_name` with
        `arguments` — and `field_path` names the number inside its answer to compare.
        Checking costs no model tokens, so a short `poll_interval_seconds` is cheap.

        It fires on the **edge**, when the condition goes from false to true, not while
        it stays true, and then holds off for `cooldown_seconds`. A condition true for an
        hour gives one run, not twelve.

        Refused if no configured tool server announces `tool_name`, and refused for the
        same unattended-work reason as `schedule_team`.
        """
        if pinned_revision_id is None:
            revision = await _call(teams, context, "GET", f"/teams/{team_id}/revisions/latest")
            pinned_revision_id = revision["id"]

        body = {
            "revision_mode": "pinned",
            "pinned_revision_id": pinned_revision_id,
            "tool_name": tool_name,
            "arguments": arguments or {},
            "field_path": field_path,
            "comparison": comparison,
            "threshold": threshold,
            "cooldown_seconds": cooldown_seconds,
            "poll_interval_seconds": poll_interval_seconds,
        }
        saved = await _call(teams, context, "POST", f"/teams/{team_id}/triggers", json=body)
        return SavedTrigger(
            trigger_id=saved["id"],
            tool_name=saved["tool_name"],
            field_path=saved["field_path"],
            comparison=saved["comparison"],
            threshold=saved["threshold"],
            enabled=saved["enabled"],
            note=_CLOCK_CAVEAT,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def list_schedules(context: Context, team_id: int) -> list[ScheduleSummary]:
        """Every schedule and trigger on this team, with its recent fires — including the
        ones that started nothing and why.

        That last part is the point: a schedule that is quiet because nothing was due and
        one that is quiet because it keeps hitting the daily ceiling look identical
        without it. A schedule the module disabled itself carries the reason it did.
        """
        schedules, triggers = await asyncio.gather(
            _call(teams, context, "GET", f"/teams/{team_id}/schedules"),
            _call(teams, context, "GET", f"/teams/{team_id}/triggers"),
        )

        # One history read per row, asked all at once rather than in a queue. Sequentially
        # this is the only tool here whose cost grows with the catalogue: ten schedules
        # would be twenty-one round trips one after another, each with its own ceiling,
        # inside a single tool call the operator is waiting on.
        histories = await asyncio.gather(
            *(_call(teams, context, "GET", f"/schedules/{row['id']}/fires") for row in schedules),
            *(_call(teams, context, "GET", f"/triggers/{row['id']}/fires") for row in triggers),
        )
        schedule_fires = histories[: len(schedules)]
        trigger_fires = histories[len(schedules) :]

        out: list[ScheduleSummary] = [
            ScheduleSummary(
                kind="schedule",
                id=row["id"],
                describes=(
                    f"cron {row['cron_expression']} (Europe/Warsaw), "
                    f"next {row['next_fire_at']} (UTC)"
                ),
                enabled=row["enabled"],
                disabled_reason=row["disabled_reason"],
                recent_fires=_recent(fires),
            )
            for row, fires in zip(schedules, schedule_fires, strict=True)
        ]
        out.extend(
            ScheduleSummary(
                kind="trigger",
                id=row["id"],
                describes=(
                    f"{row['tool_name']}.{row['field_path']} {row['comparison']} "
                    f"{row['threshold']}"
                ),
                enabled=row["enabled"],
                disabled_reason=row["disabled_reason"],
                recent_fires=_recent(fires),
            )
            for row, fires in zip(triggers, trigger_fires, strict=True)
        )
        return out


def _recent(fires: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    """The newest few, and only the fields that answer "what happened and why"."""
    return [
        {
            "at": fire["fired_at"],
            "outcome": fire["outcome"],
            "reason": fire["reason"],
            "run_id": fire["run_id"],
            "skipped_count": fire["skipped_count"],
        }
        for fire in fires[:limit]
    ]
