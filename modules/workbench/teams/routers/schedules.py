"""Schedules and triggers: a team's own clock and its own trip-wire on the market.

Every route takes `current_principal` and hands it to the store, which puts the owner
into the statement itself — the same shape `catalogue.py` and `runs.py` already carry
(specs/teams-schedules, "Harmonogram należy do operatora, który go zapisał").

Creating or editing either one resolves the revision it would run — the pinned one, or the
team's current latest — before a row is ever written, so a schedule can never point at a
revision that is not there to point at.

There is no consent check here any more, and its absence is a decision rather than an
omission: it ran on this path alone while the firing path never asked, so a schedule saved
over a read-only revision kept firing by itself once the team gained an order-placing tool
(`manage-schedules-and-drop-the-acknowledgement`). What stops an irreversible order is the
demo account the gateway enforces, the revision's own trading limits, the team's daily
ceiling, and the trace written before each order goes out.

What is deliberately *not* here: the clock that wakes on its own and claims a due fire.
That is `scheduler/`'s job, reading `store.claim_due_schedule` and
`store.claim_trigger_for_check` — these routes only create, read, edit and toggle the
rows the clock will later act on.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from .. import store
from ..auth import current_principal
from ..contract import (
    NextFiresIn,
    NextFiresOut,
    ScheduleFireOut,
    ScheduleIn,
    ScheduleOut,
    TriggerIn,
    TriggerOut,
)
from ..scheduler.timing import fires_after, next_fire_after
from ..tools import MEMORY_TOOL_NAMES, AnnouncedSnapshot, announced_snapshot
from ..validation import DefinitionRefused, check_trigger_tool

router = APIRouter()

# Bounds how far ahead a preview may reach — enough to see a daily schedule's next few
# weeks or a five-minute one's next couple of hours, and small enough that the route
# cannot be asked to roll a cron expression forward thousands of times.
_MAX_NEXT_FIRES = 20


async def _revision_must_be_there(
    request: Request,
    *,
    team_id: int,
    owner: str,
    revision_mode: str,
    pinned_revision_id: int | None,
) -> None:
    """Refuses every way the revision a schedule or trigger would run might not be there
    to point at — a team that is not the caller's, a pinned revision belonging to another
    team, a `latest` mode over a team with no revision at all.

    Called for its refusals and nothing else. It used to hand back the definition too, for
    the consent check that read the agents' tools; that check is gone, and a resolver whose
    answer nobody reads is a resolver pretending to be one.
    """
    async with request.app.state.teams.pool.acquire() as conn:
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


def _first_fire_at(cron_expression: str) -> datetime:
    return next_fire_after(cron_expression, datetime.now(UTC))


# --- schedules --------------------------------------------------------------------


@router.post("/teams/{team_id}/schedules", status_code=201)
async def create_schedule(
    team_id: int, body: ScheduleIn, request: Request, owner: str = Depends(current_principal)
) -> ScheduleOut:
    await _revision_must_be_there(
        request,
        team_id=team_id,
        owner=owner,
        revision_mode=body.revision_mode,
        pinned_revision_id=body.pinned_revision_id,
    )
    async with request.app.state.teams.pool.acquire() as conn:
        row = await store.create_schedule(
            conn,
            team_id=team_id,
            owner_principal=owner,
            revision_mode=body.revision_mode,
            pinned_revision_id=body.pinned_revision_id,
            cron_expression=body.cron(),
            next_fire_at=_first_fire_at(body.cron()),
        )
    return ScheduleOut.from_row(dict(row))


@router.get("/teams/{team_id}/schedules")
async def list_schedules(
    team_id: int, request: Request, owner: str = Depends(current_principal)
) -> list[ScheduleOut]:
    async with request.app.state.teams.pool.acquire() as conn:
        team = await store.get_team(conn, team_id=team_id, owner_principal=owner)
        if team is None:
            raise HTTPException(404, detail="no such team")
        rows = await store.list_schedules_for_team(conn, team_id=team_id, owner_principal=owner)
    return [ScheduleOut.from_row(dict(row)) for row in rows]


@router.get("/schedules/{schedule_id}")
async def get_schedule(
    schedule_id: int, request: Request, owner: str = Depends(current_principal)
) -> ScheduleOut:
    async with request.app.state.teams.pool.acquire() as conn:
        row = await store.get_schedule(conn, schedule_id=schedule_id, owner_principal=owner)
    if row is None:
        raise HTTPException(404, detail="no such schedule")
    return ScheduleOut.from_row(dict(row))


@router.put("/schedules/{schedule_id}")
async def update_schedule(
    schedule_id: int, body: ScheduleIn, request: Request, owner: str = Depends(current_principal)
) -> ScheduleOut:
    async with request.app.state.teams.pool.acquire() as conn:
        existing = await store.get_schedule(conn, schedule_id=schedule_id, owner_principal=owner)
    if existing is None:
        raise HTTPException(404, detail="no such schedule")

    await _revision_must_be_there(
        request,
        team_id=existing["team_id"],
        owner=owner,
        revision_mode=body.revision_mode,
        pinned_revision_id=body.pinned_revision_id,
    )
    async with request.app.state.teams.pool.acquire() as conn:
        row = await store.update_schedule(
            conn,
            schedule_id=schedule_id,
            owner_principal=owner,
            revision_mode=body.revision_mode,
            pinned_revision_id=body.pinned_revision_id,
            cron_expression=body.cron(),
            next_fire_at=_first_fire_at(body.cron()),
        )
    if row is None:
        raise HTTPException(404, detail="no such schedule")
    return ScheduleOut.from_row(dict(row))


@router.post("/schedules/{schedule_id}/enable")
async def enable_schedule(
    schedule_id: int, request: Request, owner: str = Depends(current_principal)
) -> ScheduleOut:
    async with request.app.state.teams.pool.acquire() as conn:
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
    async with request.app.state.teams.pool.acquire() as conn:
        row = await store.set_schedule_enabled(
            conn, schedule_id=schedule_id, owner_principal=owner, enabled=False
        )
    if row is None:
        raise HTTPException(404, detail="no such schedule")
    return ScheduleOut.from_row(dict(row))


@router.delete("/schedules/{schedule_id}", status_code=204)
async def delete_schedule(
    schedule_id: int, request: Request, owner: str = Depends(current_principal)
) -> None:
    """Gone, with its fire history. Disabling is the other thing and stays the other thing:
    a disabled schedule keeps its row and its reason and can be switched back on
    (specs/teams-schedules, "Harmonogram i wyzwalacz dają się usunąć").

    The runs it started are not touched, and nothing here has to arrange that — no column
    in `runs` points at a schedule.
    """
    async with request.app.state.teams.pool.acquire() as conn:
        deleted = await store.delete_schedule(
            conn, schedule_id=schedule_id, owner_principal=owner
        )
    if not deleted:
        raise HTTPException(404, detail="no such schedule")


@router.get("/schedules/{schedule_id}/fires")
async def get_schedule_fires(
    schedule_id: int, request: Request, owner: str = Depends(current_principal)
) -> list[ScheduleFireOut]:
    async with request.app.state.teams.pool.acquire() as conn:
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
    async with request.app.state.teams.pool.acquire() as conn:
        row = await store.get_schedule(conn, schedule_id=schedule_id, owner_principal=owner)
    if row is None:
        raise HTTPException(404, detail="no such schedule")

    return NextFiresOut(times=_take(row["cron_expression"], count))


@router.post("/schedules/next-fires")
async def preview_next_fires(
    body: NextFiresIn, _: str = Depends(current_principal)
) -> NextFiresOut:
    """The same answer for a timing nobody has saved (specs/teams-schedules, "Moduł liczy
    najbliższe wyzwolenia także dla opisu, którego nie zapisano").

    It touches no row, so it takes no team and no ownership check beyond being signed in —
    what it answers about is the operator's own draft, and a cron expression is not
    somebody's data. `NextFiresIn` is `ScheduleIn`'s own timing half, so a draft that
    previews here is a draft the save will accept.
    """
    if not 1 <= body.count <= _MAX_NEXT_FIRES:
        raise HTTPException(422, detail=f"count must be between 1 and {_MAX_NEXT_FIRES}")
    return NextFiresOut(times=_take(body.cron(), body.count))


def _take(cron_expression: str, count: int) -> list[datetime]:
    fires = fires_after(cron_expression, datetime.now(UTC))
    return [next(fires) for _ in range(count)]


# --- triggers -----------------------------------------------------------------------


def _check_trigger_tool(tool_name: str, *, announced: AnnouncedSnapshot) -> None:
    # A trigger's condition is a reading of the world, taken with a *tool server's* tools
    # (specs/teams-triggers, "Warunek jest czytany narzędziami serwera narzędzi"), so the
    # tools this process serves itself are subtracted before the check. A team's memory is
    # not the world, and it has no run to be read inside of when the clock is the caller —
    # a trigger naming one would be a condition that could never come true.
    #
    # No server configured at all is passed on as `None`, which is the shape
    # `check_trigger_tool` writes its own refusal for; a configured server that could not
    # be asked comes back inside the snapshot under `unreachable` instead, and a name
    # nobody announces is refused the same way whichever silence it was.
    names = (
        sorted(set(announced.by_name) - MEMORY_TOOL_NAMES)
        if announced.configured_servers
        else None
    )
    try:
        check_trigger_tool(tool_name, announced_tools=names)
    except DefinitionRefused as err:
        raise HTTPException(422, detail=str(err)) from err


@router.post("/teams/{team_id}/triggers", status_code=201)
async def create_trigger(
    team_id: int, body: TriggerIn, request: Request, owner: str = Depends(current_principal)
) -> TriggerOut:
    await _revision_must_be_there(
        request,
        team_id=team_id,
        owner=owner,
        revision_mode=body.revision_mode,
        pinned_revision_id=body.pinned_revision_id,
    )
    announced = await announced_snapshot(request.app.state.teams.settings)
    _check_trigger_tool(body.tool_name, announced=announced)

    async with request.app.state.teams.pool.acquire() as conn:
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
        )
    return TriggerOut.from_row(dict(row))


@router.get("/teams/{team_id}/triggers")
async def list_triggers(
    team_id: int, request: Request, owner: str = Depends(current_principal)
) -> list[TriggerOut]:
    async with request.app.state.teams.pool.acquire() as conn:
        team = await store.get_team(conn, team_id=team_id, owner_principal=owner)
        if team is None:
            raise HTTPException(404, detail="no such team")
        rows = await store.list_triggers_for_team(conn, team_id=team_id, owner_principal=owner)
    return [TriggerOut.from_row(dict(row)) for row in rows]


@router.get("/triggers/{trigger_id}")
async def get_trigger(
    trigger_id: int, request: Request, owner: str = Depends(current_principal)
) -> TriggerOut:
    async with request.app.state.teams.pool.acquire() as conn:
        row = await store.get_trigger(conn, trigger_id=trigger_id, owner_principal=owner)
    if row is None:
        raise HTTPException(404, detail="no such trigger")
    return TriggerOut.from_row(dict(row))


@router.put("/triggers/{trigger_id}")
async def update_trigger(
    trigger_id: int, body: TriggerIn, request: Request, owner: str = Depends(current_principal)
) -> TriggerOut:
    async with request.app.state.teams.pool.acquire() as conn:
        existing = await store.get_trigger(conn, trigger_id=trigger_id, owner_principal=owner)
    if existing is None:
        raise HTTPException(404, detail="no such trigger")

    await _revision_must_be_there(
        request,
        team_id=existing["team_id"],
        owner=owner,
        revision_mode=body.revision_mode,
        pinned_revision_id=body.pinned_revision_id,
    )
    announced = await announced_snapshot(request.app.state.teams.settings)
    _check_trigger_tool(body.tool_name, announced=announced)

    async with request.app.state.teams.pool.acquire() as conn:
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
        )
    if row is None:
        raise HTTPException(404, detail="no such trigger")
    return TriggerOut.from_row(dict(row))


@router.post("/triggers/{trigger_id}/enable")
async def enable_trigger(
    trigger_id: int, request: Request, owner: str = Depends(current_principal)
) -> TriggerOut:
    async with request.app.state.teams.pool.acquire() as conn:
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
    async with request.app.state.teams.pool.acquire() as conn:
        row = await store.set_trigger_enabled(
            conn, trigger_id=trigger_id, owner_principal=owner, enabled=False
        )
    if row is None:
        raise HTTPException(404, detail="no such trigger")
    return TriggerOut.from_row(dict(row))


@router.delete("/triggers/{trigger_id}", status_code=204)
async def delete_trigger(
    trigger_id: int, request: Request, owner: str = Depends(current_principal)
) -> None:
    """The same as deleting a schedule, for the other half of the pair."""
    async with request.app.state.teams.pool.acquire() as conn:
        deleted = await store.delete_trigger(conn, trigger_id=trigger_id, owner_principal=owner)
    if not deleted:
        raise HTTPException(404, detail="no such trigger")


@router.get("/triggers/{trigger_id}/fires")
async def get_trigger_fires(
    trigger_id: int, request: Request, owner: str = Depends(current_principal)
) -> list[ScheduleFireOut]:
    async with request.app.state.teams.pool.acquire() as conn:
        trigger = await store.get_trigger(conn, trigger_id=trigger_id, owner_principal=owner)
        if trigger is None:
            raise HTTPException(404, detail="no such trigger")
        rows = await store.list_fires_for_trigger(
            conn, trigger_id=trigger_id, owner_principal=owner
        )
    return [ScheduleFireOut.from_row(dict(row)) for row in rows]
