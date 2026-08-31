"""Runs: starting one, reading its trace, watching it work, and interrupting it, with every route handing
`current_principal` to the store. A run is started on a *revision*, so a save while it works changes nothing about it."""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from .. import store
from ..auth import current_principal
from ..contract import RunOut, RunStepOut, ToolCallOut, TradeOut
from ..runner import RunFinished, StepFinished, StepStarted, ToolCalled, start_run_on_revision
from ..runner.cost import DailyCostLimitReached
from ..runner.trading import DailyOrderLimitReached
from ..validation import DefinitionRefused

log = logging.getLogger(__name__)

router = APIRouter()

# How often a silent stream gets a keep-alive comment. App Service drops a connection idle
# for 230s; a run can easily be quiet for longer than that while one agent thinks.
_KEEPALIVE_SECONDS = 15


@router.post("/teams/{team_id}/runs", status_code=201)
async def start_run(
    team_id: int, request: Request, owner: str = Depends(current_principal)
) -> RunOut:
    """Starts a run of the team's latest revision and answers immediately. 201 with the run, not its
    result: a team takes minutes, and a request held open for that fails whenever the network does.

    The checks and the start itself are `runner.start_run_on_revision` — the same function the clock calls
    once it has resolved its own revision."""
    pool = request.app.state.teams.pool
    async with pool.acquire() as conn:
        revision = await store.get_latest_revision(conn, team_id=team_id, owner_principal=owner)
    if revision is None:
        raise HTTPException(404, detail="no such team")

    try:
        # Every check and the start itself live in `start_run_on_revision`: the model catalogue, the daily
        # cost ceiling and the daily order ceiling. A schedule firing at 3am takes exactly the same ones.
        run, _task = await start_run_on_revision(
            pool,
            revision=dict(revision),
            owner_principal=owner,
            catalogue=request.app.state.teams.catalogue,
            provider=request.app.state.teams.provider,
            tool_registry=request.app.state.teams.tools,
            settings=request.app.state.teams.settings,
            registry=request.app.state.teams.runs,
        )
    except DefinitionRefused as err:
        raise HTTPException(422, detail=str(err)) from err
    except (DailyCostLimitReached, DailyOrderLimitReached) as err:
        # Both are 422 and both name their own number — after "why did nothing start" the operator's next
        # question is "how much of what".
        raise HTTPException(422, detail=str(err)) from err
    return RunOut.from_row(dict(run))


@router.get("/teams/{team_id}/runs")
async def list_runs(
    team_id: int, request: Request, owner: str = Depends(current_principal)
) -> list[RunOut]:
    """Every run of this team, newest first — including runs of revisions since replaced,
    which is what makes two of them comparable at all."""
    async with request.app.state.teams.pool.acquire() as conn:
        team = await store.get_team(conn, team_id=team_id, owner_principal=owner)
        if team is None:
            raise HTTPException(404, detail="no such team")
        rows = await store.list_runs_for_team(conn, team_id=team_id, owner_principal=owner)
    return [RunOut.from_row(dict(row)) for row in rows]


@router.get("/runs/{run_id}")
async def get_run(run_id: int, request: Request, owner: str = Depends(current_principal)) -> RunOut:
    async with request.app.state.teams.pool.acquire() as conn:
        row = await store.get_run(conn, run_id=run_id, owner_principal=owner)
    if row is None:
        raise HTTPException(404, detail="no such run")
    return RunOut.from_row(dict(row))


@router.get("/runs/{run_id}/steps")
async def get_run_steps(
    run_id: int, request: Request, owner: str = Depends(current_principal)
) -> list[RunStepOut]:
    """Who is waiting, who is working, who has finished and what they handed over — the same picture the
    progress stream carries, for a viewer that arrived late or came back."""
    async with request.app.state.teams.pool.acquire() as conn:
        run = await store.get_run(conn, run_id=run_id, owner_principal=owner)
        if run is None:
            raise HTTPException(404, detail="no such run")
        rows = await store.get_run_steps(conn, run_id=run_id)
    return [RunStepOut.from_row(dict(row)) for row in rows]


@router.get("/runs/{run_id}/tool-calls")
async def get_run_tool_calls(
    run_id: int, request: Request, owner: str = Depends(current_principal)
) -> list[ToolCallOut]:
    async with request.app.state.teams.pool.acquire() as conn:
        run = await store.get_run(conn, run_id=run_id, owner_principal=owner)
        if run is None:
            raise HTTPException(404, detail="no such run")
        rows = await store.get_run_tool_calls(conn, run_id=run_id)
    return [ToolCallOut.from_row(dict(row)) for row in rows]


@router.get("/runs/{run_id}/trades")
async def get_run_trades(
    run_id: int, request: Request, owner: str = Depends(current_principal)
) -> list[TradeOut]:
    """What this run did to the account, in the order it did it. Beside `/tool-calls` rather than folded
    into it: that route answers what the agents asked for, this one what happened to the money."""
    async with request.app.state.teams.pool.acquire() as conn:
        run = await store.get_run(conn, run_id=run_id, owner_principal=owner)
        if run is None:
            raise HTTPException(404, detail="no such run")
        rows = await store.get_run_trades(conn, run_id=run_id)
    return [TradeOut.from_row(dict(row)) for row in rows]


@router.post("/runs/{run_id}/cancel", status_code=202)
async def cancel_run(
    run_id: int, request: Request, owner: str = Depends(current_principal)
) -> RunOut:
    """Asks a run to stop. 202, not 200: the status is written by the run itself as it unwinds, so what
    comes back is the run as it was when the interruption was accepted."""
    async with request.app.state.teams.pool.acquire() as conn:
        row = await store.get_run(conn, run_id=run_id, owner_principal=owner)
    if row is None:
        raise HTTPException(404, detail="no such run")
    if row["status"] not in ("pending", "running"):
        raise HTTPException(409, detail=f"the run is already {row['status']}")
    if not request.app.state.teams.runs.cancel(run_id):
        # In the database as running, but nothing in this process is running it — the state
        # `store.fail_unfinished_runs` closes at start-up. 409 rather than pretending to interrupt.
        raise HTTPException(409, detail="the run is not being worked on by this instance")
    return RunOut.from_row(dict(row))


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.get("/runs/{run_id}/events")
async def run_events(
    run_id: int, request: Request, owner: str = Depends(current_principal)
) -> StreamingResponse:
    """Progress as it happens, starting with where the run is now. A viewer that opens halfway through has
    to see the agents that already finished, and dropping the connection unsubscribes a queue and nothing else."""
    pool = request.app.state.teams.pool
    registry = request.app.state.teams.runs
    # Subscribed before the snapshot is *read*, not merely before it is sent: releasing the connection is a suspension
    # point, so a step finishing there landed in neither place. A repeated event is the direction to fail in.
    queue = registry.subscribe(run_id)
    try:
        async with pool.acquire() as conn:
            run = await store.get_run(conn, run_id=run_id, owner_principal=owner)
            if run is None:
                raise HTTPException(404, detail="no such run")
            steps = await store.get_run_steps(conn, run_id=run_id)
    except BaseException:
        registry.unsubscribe(run_id, queue)
        raise

    snapshot = {
        "run": RunOut.from_row(dict(run)).model_dump(mode="json"),
        "steps": [RunStepOut.from_row(dict(row)).model_dump(mode="json") for row in steps],
    }
    finished = run["status"] not in ("pending", "running")

    async def event_stream():
        try:
            yield _sse("snapshot", snapshot)
            if finished:
                # Nothing more will happen to this run. Said rather than left open: a
                # stream that never ends looks exactly like a run that never finishes.
                return
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=_KEEPALIVE_SECONDS)
                except TimeoutError:
                    yield ": ping\n\n"
                    continue
                if event is None:
                    return
                if isinstance(event, StepStarted):
                    yield _sse("step_started", {"agent_key": event.agent_key})
                elif isinstance(event, StepFinished):
                    yield _sse(
                        "step_finished",
                        {
                            "agent_key": event.agent_key,
                            "status": event.status,
                            "output": event.output,
                        },
                    )
                elif isinstance(event, ToolCalled):
                    yield _sse(
                        "tool_call",
                        {
                            "agent_key": event.agent_key,
                            "round_index": event.call.round_index,
                            "position": event.call.position,
                            "tool_name": event.call.name,
                            "outcome": event.call.outcome,
                            "duration_ms": event.call.duration_ms,
                        },
                    )
                elif isinstance(event, RunFinished):
                    yield _sse(
                        "run_finished",
                        {"status": event.status, "stopped_reason": event.stopped_reason},
                    )
        finally:
            registry.unsubscribe(run_id, queue)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
