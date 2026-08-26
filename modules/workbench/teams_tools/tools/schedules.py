"""Putting a team on a clock or on a market condition — and everything after that: pausing, editing and
deleting what is already there. The whole set, because the operator who sets a schedule with a sentence
corrects it with a sentence too.

Pausing and deleting are two tools rather than one with a flag: they differ in what cannot be undone, and a
model choosing between them should have to name which it means."""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from mcp.server.fastmcp import Context, FastMCP
from pydantic import BaseModel, Field

from ..client import TeamsClient
from ._shared import DESTRUCTIVE, READ_ONLY, WRITE, _call

# Said on every schedule and trigger this module creates. It over-warns on purpose: the clock's own setting
# is teams' and is not on its wire, so this module cannot tell a running clock from a stopped one.
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

        Use `edit_schedule` to change the time of one that already exists, rather than
        making a second schedule beside it.
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

        Refused if no configured tool server announces `tool_name`.
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

        # One history read per row, asked all at once rather than in a queue: sequentially this is the only
        # tool here whose cost grows with the catalogue, inside a single call the operator is waiting on.
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


    @mcp.tool(annotations=WRITE)
    async def pause_schedule(context: Context, schedule_id: int, resume: bool = False) -> str:
        """Stop a schedule from firing, or start it again — without deleting it.

        A paused schedule keeps its row, its history and its identifier; resuming it also
        clears whatever streak of failures had switched it off. This is the reversible
        half of the pair: `delete_schedule` is the other one and there is no undoing it.
        """
        action = "enable" if resume else "disable"
        row = await _call(teams, context, "POST", f"/schedules/{schedule_id}/{action}")
        return (
            f"schedule {row['id']} is now {'enabled' if row['enabled'] else 'paused'}"
            f" — cron {row['cron_expression']}, next {row['next_fire_at']} (UTC)"
        )

    @mcp.tool(annotations=WRITE)
    async def pause_trigger(context: Context, trigger_id: int, resume: bool = False) -> str:
        """Stop a trigger from firing, or start it again — the same as `pause_schedule`,
        for a trigger."""
        action = "enable" if resume else "disable"
        row = await _call(teams, context, "POST", f"/triggers/{trigger_id}/{action}")
        return f"trigger {row['id']} is now {'enabled' if row['enabled'] else 'paused'}"

    @mcp.tool(annotations=WRITE)
    async def edit_schedule(
        context: Context,
        schedule_id: int,
        cron_expression: str = Field(
            description=(
                "five-field cron, read as a wall clock in Poland (Europe/Warsaw). Weekdays "
                "go in the fifth field — '35 * * * 1,2,3,4,5' is every hour at :35 on "
                "trading days"
            )
        ),
        pinned_revision_id: int | None = None,
    ) -> SavedSchedule:
        """Change when an existing schedule fires, keeping the schedule itself.

        The row, its identifier and its fire history stay; only the timing changes. Do not
        reach for `delete_schedule` followed by `schedule_team` to do this — that is a
        different schedule with an empty history and a number the operator was not talking
        about.

        `pinned_revision_id` left out keeps whichever revision the schedule already runs.
        """
        current = await _call(teams, context, "GET", f"/schedules/{schedule_id}")
        body = {
            "revision_mode": current["revision_mode"],
            "pinned_revision_id": pinned_revision_id
            if pinned_revision_id is not None
            else current["pinned_revision_id"],
            "cron_expression": cron_expression,
        }
        saved = await _call(teams, context, "PUT", f"/schedules/{schedule_id}", json=body)
        return SavedSchedule(
            schedule_id=saved["id"],
            cron_expression=saved["cron_expression"],
            next_fire_at=saved["next_fire_at"],
            enabled=saved["enabled"],
            note=_CLOCK_CAVEAT,
        )

    @mcp.tool(annotations=WRITE)
    async def edit_trigger(
        context: Context,
        trigger_id: int,
        threshold: str | None = None,
        comparison: Literal["gt", "gte", "lt", "lte", "eq"] | None = None,
        cooldown_seconds: int | None = None,
        poll_interval_seconds: int | None = None,
    ) -> SavedTrigger:
        """Change an existing trigger's condition or its pacing, keeping the trigger.

        Every argument left out stays as it is — the condition's tool and field are not
        editable here on purpose: a trigger watching a different number is a different
        trigger, and deserves to be created as one.
        """
        # `is not None`, not `or`. Zero is falsy and `cooldown_seconds=0` reads as "fire every time"; under
        # `or` it kept the old value and answered with a success naming it. Forwarding lets teams refuse.
        current = await _call(teams, context, "GET", f"/triggers/{trigger_id}")
        body = {
            "revision_mode": current["revision_mode"],
            "pinned_revision_id": current["pinned_revision_id"],
            "tool_name": current["tool_name"],
            "arguments": current["arguments"],
            "field_path": current["field_path"],
            "comparison": comparison if comparison is not None else current["comparison"],
            "threshold": threshold if threshold is not None else current["threshold"],
            "cooldown_seconds": cooldown_seconds
            if cooldown_seconds is not None
            else current["cooldown_seconds"],
            "poll_interval_seconds": poll_interval_seconds
            if poll_interval_seconds is not None
            else current["poll_interval_seconds"],
        }
        saved = await _call(teams, context, "PUT", f"/triggers/{trigger_id}", json=body)
        return SavedTrigger(
            trigger_id=saved["id"],
            tool_name=saved["tool_name"],
            field_path=saved["field_path"],
            comparison=saved["comparison"],
            threshold=saved["threshold"],
            enabled=saved["enabled"],
            note=_CLOCK_CAVEAT,
        )

    @mcp.tool(annotations=DESTRUCTIVE)
    async def delete_schedule(context: Context, schedule_id: int) -> str:
        """Delete a schedule for good. One schedule per call, by its identifier.

        **Its fire history goes with it and does not come back** — every record of when it
        fired, what it skipped and why. What stays is the work itself: the runs it started,
        with their cost and any orders they placed, because those belong to the run rather
        than to the schedule that ordered it.

        To stop a schedule without losing any of that, use `pause_schedule`.
        """
        await _call(teams, context, "DELETE", f"/schedules/{schedule_id}")
        return (
            f"schedule {schedule_id} is deleted, together with its fire history. "
            "The runs it started are untouched, and so is what they cost."
        )

    @mcp.tool(annotations=DESTRUCTIVE)
    async def delete_trigger(context: Context, trigger_id: int) -> str:
        """Delete a trigger for good, with its fire history — the same as
        `delete_schedule`, for a trigger. The runs it started stay. `pause_trigger` is the
        reversible way to make it stop."""
        await _call(teams, context, "DELETE", f"/triggers/{trigger_id}")
        return (
            f"trigger {trigger_id} is deleted, together with its fire history. "
            "The runs it started are untouched, and so is what they cost."
        )


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
