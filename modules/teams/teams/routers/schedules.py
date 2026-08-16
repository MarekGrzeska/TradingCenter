"""Schedules and triggers: a team's own clock and its own trip-wire on the market.

Every route takes `current_principal` and hands it to the store, which puts the owner
into the statement itself — the same shape `catalogue.py` and `runs.py` already carry
(specs/teams-schedules, "Harmonogram należy do operatora, który go zapisał").

Creating or editing either one resolves the revision it would run — the pinned one, or
the team's current latest — and runs `validation.check_unattended` against it before a
row is ever written: a schedule or trigger over a revision whose agents carry a
state-changing tool is refused unless it carries an explicit acknowledgement
(specs/teams-schedules). No such tool exists yet, so every save today takes the
unremarkable branch — the refusal is real code, exercised by one test, waiting for the
day a tool answers it (design.md, "Punkty styku z fazą 2").

What is deliberately *not* here: the clock that wakes on its own and claims a due fire.
That is `scheduler/`'s job, reading `store.claim_due_schedule` and
`store.claim_trigger_for_check` — these routes only create, read, edit and toggle the
rows the clock will later act on.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from croniter import croniter
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from .. import store
from ..auth import current_principal
from ..contract import (
    NextFiresOut,
    ScheduleFireOut,
    ScheduleIn,
    ScheduleOut,
    TeamDefinition,
    TeamRevisionOut,
    TriggerIn,
    TriggerOut,
)
from ..tools import announced_tool_names
from ..validation import DefinitionRefused, check_trigger_tool, check_unattended

router = APIRouter()

# Bounds how far ahead a preview may reach — enough to see a daily schedule's next few
# weeks or a five-minute one's next couple of hours, and small enough that the route
# cannot be asked to roll a cron expression forward thousands of times.
_MAX_NEXT_FIRES = 20


async def _resolve_definition(
    request: Request,
    *,
    team_id: int,
    owner: str,
    revision_mode: str,
    pinned_revision_id: int | None,
) -> TeamDefinition:
    """The definition a schedule or trigger would put to work — the pinned revision, or
    the team's latest right now for `revision_mode='latest'`. Raises `HTTPException` for
    every way that revision might not be there to point at.
    """
    async with request.app.state.pool.acquire() as conn:
        team = await store.get_team(conn, team_id=team_id, owner_principal=owner)
        if team is None:
            raise HTTPException(404, detail="no such team")

        if revision_mode == "pinned":
            assert pinned_revision_id is not None  # enforced by ScheduleIn/TriggerIn
            revision = await store.get_revision_by_id(
                conn, revision_id=pinned_revision_id, owner_principal=owner
            )
            if revision is None or revision["team_id"] != team_id:
                raise HTTPException(
                    422,
                    detail=f"revision {pinned_revision_id} does not belong to team {team_id}",
                )
        else:
            revision = await store.get_latest_revision(conn, team_id=team_id, owner_principal=owner)
            if revision is None:
                raise HTTPException(404, detail="no such team")

    return TeamRevisionOut.from_row(dict(revision)).definition


def _check_unattended(definition: TeamDefinition, *, unattended_ack: bool) -> None:
    try:
        check_unattended(definition, unattended_ack=unattended_ack)
    except DefinitionRefused as err:
        raise HTTPException(422, detail=str(err)) from err


def _first_fire_at(cron_expression: str) -> datetime:
    return croniter(cron_expression, datetime.now(UTC)).get_next(datetime)


# --- schedules --------------------------------------------------------------------


@router.post("/teams/{team_id}/schedules", status_code=201)
async def create_schedule(
    team_id: int, body: ScheduleIn, request: Request, owner: str = Depends(current_principal)
) -> ScheduleOut:
    definition = await _resolve_definition(
        request,
        team_id=team_id,
        owner=owner,
        revision_mode=body.revision_mode,
        pinned_revision_id=body.pinned_revision_id,
    )
    _check_unattended(definition, unattended_ack=body.unattended_ack)

    async with request.app.state.pool.acquire() as conn:
        row = await store.create_schedule(
            conn,
            team_id=team_id,
            owner_principal=owner,
            revision_mode=body.revision_mode,
            pinned_revision_id=body.pinned_revision_id,
            cron_expression=body.cron_expression,
            next_fire_at=_first_fire_at(body.cron_expression),
            unattended_ack=body.unattended_ack,
        )
    return ScheduleOut.from_row(dict(row))


@router.get("/teams/{team_id}/schedules")
async def list_schedules(
    team_id: int, request: Request, owner: str = Depends(current_principal)
) -> list[ScheduleOut]:
    async with request.app.state.pool.acquire() as conn:
        team = await store.get_team(conn, team_id=team_id, owner_principal=owner)
        if team is None:
            raise HTTPException(404, detail="no such team")
        rows = await store.list_schedules_for_team(conn, team_id=team_id, owner_principal=owner)
    return [ScheduleOut.from_row(dict(row)) for row in rows]


@router.get("/schedules/{schedule_id}")
async def get_schedule(
    schedule_id: int, request: Request, owner: str = Depends(current_principal)
) -> ScheduleOut:
    async with request.app.state.pool.acquire() as conn:
        row = await store.get_schedule(conn, schedule_id=schedule_id, owner_principal=owner)
    if row is None:
        raise HTTPException(404, detail="no such schedule")
    return ScheduleOut.from_row(dict(row))


@router.put("/schedules/{schedule_id}")
async def update_schedule(
    schedule_id: int, body: ScheduleIn, request: Request, owner: str = Depends(current_principal)
) -> ScheduleOut:
    async with request.app.state.pool.acquire() as conn:
        existing = await store.get_schedule(conn, schedule_id=schedule_id, owner_principal=owner)
    if existing is None:
        raise HTTPException(404, detail="no such schedule")

    definition = await _resolve_definition(
        request,
        team_id=existing["team_id"],
        owner=owner,
        revision_mode=body.revision_mode,
        pinned_revision_id=body.pinned_revision_id,
    )
    _check_unattended(definition, unattended_ack=body.unattended_ack)

    async with request.app.state.pool.acquire() as conn:
        row = await store.update_schedule(
            conn,
            schedule_id=schedule_id,
            owner_principal=owner,
            revision_mode=body.revision_mode,
            pinned_revision_id=body.pinned_revision_id,
            cron_expression=body.cron_expression,
            next_fire_at=_first_fire_at(body.cron_expression),
            unattended_ack=body.unattended_ack,
        )
    if row is None:
        raise HTTPException(404, detail="no such schedule")
    return ScheduleOut.from_row(dict(row))


@router.post("/schedules/{schedule_id}/enable")
async def enable_schedule(
    schedule_id: int, request: Request, owner: str = Depends(current_principal)
) -> ScheduleOut:
    async with request.app.state.pool.acquire() as conn:
        row = await store.set_schedule_enabled(
            conn, schedule_id=schedule_id, owner_principal=owner, enabled=True
        )
    if row is None:
        raise HTTPException(404, detail="no such schedule")
    return ScheduleOut.from_row(dict(row))


@router.post("/schedules/{schedule_id}/disable")
async def disable_schedule(
    schedule_id: int, request: Request, owner: str = Depends(current_principal)
) -> ScheduleOut:
    async with request.app.state.pool.acquire() as conn:
        row = await store.set_schedule_enabled(
            conn, schedule_id=schedule_id, owner_principal=owner, enabled=False
        )
    if row is None:
        raise HTTPException(404, detail="no such schedule")
    return ScheduleOut.from_row(dict(row))


@router.get("/schedules/{schedule_id}/fires")
async def get_schedule_fires(
    schedule_id: int, request: Request, owner: str = Depends(current_principal)
) -> list[ScheduleFireOut]:
    async with request.app.state.pool.acquire() as conn:
        schedule = await store.get_schedule(conn, schedule_id=schedule_id, owner_principal=owner)
        if schedule is None:
            raise HTTPException(404, detail="no such schedule")
        rows = await store.list_fires_for_schedule(
            conn, schedule_id=schedule_id, owner_principal=owner
        )
    return [ScheduleFireOut.from_row(dict(row)) for row in rows]


@router.get("/schedules/{schedule_id}/next-fires")
async def next_fires(
    schedule_id: int,
    request: Request,
    owner: str = Depends(current_principal),
    count: int = Query(default=5, ge=1, le=_MAX_NEXT_FIRES),
) -> NextFiresOut:
    """specs/terminal-teams-schedules, "Terminal nie liczy czasu wyzwolenia sam" — every
    time in the answer is rolled forward from now by this module, not the row's stored
    `next_fire_at`, which only reflects the last claim."""
    async with request.app.state.pool.acquire() as conn:
        row = await store.get_schedule(conn, schedule_id=schedule_id, owner_principal=owner)
    if row is None:
        raise HTTPException(404, detail="no such schedule")

    iterator = croniter(row["cron_expression"], datetime.now(UTC))
    times = [iterator.get_next(datetime) for _ in range(count)]
    return NextFiresOut(times=times)


# --- triggers -----------------------------------------------------------------------


async def _check_trigger_tool(request: Request, tool_name: str) -> None:
    # `announced_tool_names` already turns "not configured" and "configured but
    # unreachable" into the same `None` — the save path does not need to tell them apart
    # (`tools/assignment.py`'s own docstring on why).
    announced = await announced_tool_names(request.app.state.settings)
    try:
        check_trigger_tool(tool_name, announced_tools=announced)
    except DefinitionRefused as err:
        raise HTTPException(422, detail=str(err)) from err


@router.post("/teams/{team_id}/triggers", status_code=201)
async def create_trigger(
    team_id: int, body: TriggerIn, request: Request, owner: str = Depends(current_principal)
) -> TriggerOut:
    definition = await _resolve_definition(
        request,
        team_id=team_id,
        owner=owner,
        revision_mode=body.revision_mode,
        pinned_revision_id=body.pinned_revision_id,
    )
    _check_unattended(definition, unattended_ack=body.unattended_ack)
    await _check_trigger_tool(request, body.tool_name)

    async with request.app.state.pool.acquire() as conn:
        row = await store.create_trigger(
            conn,
            team_id=team_id,
            owner_principal=owner,
            revision_mode=body.revision_mode,
            pinned_revision_id=body.pinned_revision_id,
            tool_name=body.tool_name,
            arguments=body.arguments,
            field_path=body.field_path,
            comparison=body.comparison,
            threshold=Decimal(body.threshold),
            cooldown_seconds=body.cooldown_seconds,
            poll_interval_seconds=body.poll_interval_seconds,
            next_check_at=datetime.now(UTC),
            unattended_ack=body.unattended_ack,
        )
    return TriggerOut.from_row(dict(row))


@router.get("/teams/{team_id}/triggers")
async def list_triggers(
    team_id: int, request: Request, owner: str = Depends(current_principal)
) -> list[TriggerOut]:
    async with request.app.state.pool.acquire() as conn:
        team = await store.get_team(conn, team_id=team_id, owner_principal=owner)
        if team is None:
            raise HTTPException(404, detail="no such team")
        rows = await store.list_triggers_for_team(conn, team_id=team_id, owner_principal=owner)
    return [TriggerOut.from_row(dict(row)) for row in rows]


@router.get("/triggers/{trigger_id}")
async def get_trigger(
    trigger_id: int, request: Request, owner: str = Depends(current_principal)
) -> TriggerOut:
    async with request.app.state.pool.acquire() as conn:
        row = await store.get_trigger(conn, trigger_id=trigger_id, owner_principal=owner)
    if row is None:
        raise HTTPException(404, detail="no such trigger")
    return TriggerOut.from_row(dict(row))


@router.put("/triggers/{trigger_id}")
async def update_trigger(
    trigger_id: int, body: TriggerIn, request: Request, owner: str = Depends(current_principal)
) -> TriggerOut:
    async with request.app.state.pool.acquire() as conn:
        existing = await store.get_trigger(conn, trigger_id=trigger_id, owner_principal=owner)
    if existing is None:
        raise HTTPException(404, detail="no such trigger")

    definition = await _resolve_definition(
        request,
        team_id=existing["team_id"],
        owner=owner,
        revision_mode=body.revision_mode,
        pinned_revision_id=body.pinned_revision_id,
    )
    _check_unattended(definition, unattended_ack=body.unattended_ack)
    await _check_trigger_tool(request, body.tool_name)

    async with request.app.state.pool.acquire() as conn:
        row = await store.update_trigger(
            conn,
            trigger_id=trigger_id,
            owner_principal=owner,
            revision_mode=body.revision_mode,
            pinned_revision_id=body.pinned_revision_id,
            tool_name=body.tool_name,
            arguments=body.arguments,
            field_path=body.field_path,
            comparison=body.comparison,
            threshold=Decimal(body.threshold),
            cooldown_seconds=body.cooldown_seconds,
            poll_interval_seconds=body.poll_interval_seconds,
            unattended_ack=body.unattended_ack,
        )
    if row is None:
        raise HTTPException(404, detail="no such trigger")
    return TriggerOut.from_row(dict(row))


@router.post("/triggers/{trigger_id}/enable")
async def enable_trigger(
    trigger_id: int, request: Request, owner: str = Depends(current_principal)
) -> TriggerOut:
    async with request.app.state.pool.acquire() as conn:
        row = await store.set_trigger_enabled(
            conn, trigger_id=trigger_id, owner_principal=owner, enabled=True
        )
    if row is None:
        raise HTTPException(404, detail="no such trigger")
    return TriggerOut.from_row(dict(row))


@router.post("/triggers/{trigger_id}/disable")
async def disable_trigger(
    trigger_id: int, request: Request, owner: str = Depends(current_principal)
) -> TriggerOut:
    async with request.app.state.pool.acquire() as conn:
        row = await store.set_trigger_enabled(
            conn, trigger_id=trigger_id, owner_principal=owner, enabled=False
        )
    if row is None:
        raise HTTPException(404, detail="no such trigger")
    return TriggerOut.from_row(dict(row))


@router.get("/triggers/{trigger_id}/fires")
async def get_trigger_fires(
    trigger_id: int, request: Request, owner: str = Depends(current_principal)
) -> list[ScheduleFireOut]:
    async with request.app.state.pool.acquire() as conn:
        trigger = await store.get_trigger(conn, trigger_id=trigger_id, owner_principal=owner)
        if trigger is None:
            raise HTTPException(404, detail="no such trigger")
        rows = await store.list_fires_for_trigger(
            conn, trigger_id=trigger_id, owner_principal=owner
        )
    return [ScheduleFireOut.from_row(dict(row)) for row in rows]
