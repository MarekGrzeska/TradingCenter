"""Runs: starting one, reading its trace, watching it work, and interrupting it.

Every route takes `current_principal` and hands it to the store, which puts the owner into
the statement itself — a run belonging to somebody else answers 404, exactly as one that
never existed (specs/teams-browser-access).

A run is started on a **revision**, never on "the team as it is now": the route resolves
the revision once, and everything after that — the graph, the trace, the comparison a
month later — points at that row. An operator saving a new revision while a run works
changes nothing about the run (specs/teams-runs, "Przebieg odbywa się na rewizji, nie na
zespole").
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from .. import store
from ..auth import current_principal
from ..contract import RunOut, RunStepOut, TeamRevisionOut, ToolCallOut
from ..runner import RunFinished, StepFinished, StepStarted, ToolCalled, execute_run
from ..validation import DefinitionRefused, check_runnable

log = logging.getLogger(__name__)

router = APIRouter()

# How often a silent stream gets a keep-alive comment. App Service drops a connection idle
# for 230s; a run can easily be quiet for longer than that while one agent thinks.
_KEEPALIVE_SECONDS = 15


@router.post("/teams/{team_id}/runs", status_code=201)
async def start_run(
    team_id: int, request: Request, owner: str = Depends(current_principal)
) -> RunOut:
    """Starts a run of the team's latest revision and answers immediately.

    201 with the run, not the run's result: a team takes minutes, and a request held open
    for it would be a request that fails whenever the network does. What the operator
    watches afterwards is `/runs/{id}/events`, and what survives either way is the trace.
    """
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        revision = await store.get_latest_revision(conn, team_id=team_id, owner_principal=owner)
    if revision is None:
        raise HTTPException(404, detail="no such team")

    # Through the wire model rather than by parsing the JSONB here: `TeamRevisionOut` is
    # already the one place that knows how a stored definition is read back.
    definition = TeamRevisionOut.from_row(dict(revision)).definition
    try:
        # The saved revision, checked again now — a model dropped from the configuration
        # since it was saved is exactly what this is for (specs/teams-models). The tool
        # half of the same question is asked by the engine, which needs a session to ask
        # it with.
        check_runnable(definition, model_ids=request.app.state.catalogue.ids())
    except DefinitionRefused as err:
        raise HTTPException(422, detail=str(err)) from err

    async with pool.acquire() as conn:
        run, _steps = await store.create_run(
            conn,
            team_revision_id=revision["id"],
            owner_principal=owner,
            agent_keys=[agent.key for agent in definition.agents],
        )

    registry = request.app.state.runs
    task = asyncio.create_task(
        execute_run(
            pool,
            run_id=run["id"],
            definition=definition,
            provider=request.app.state.provider,
            tool_server=request.app.state.tools,
            catalogue=request.app.state.catalogue,
            settings=request.app.state.settings,
            registry=registry,
        )
    )
    registry.register(run["id"], task)
    return RunOut.from_row(dict(run))


@router.get("/teams/{team_id}/runs")
async def list_runs(
    team_id: int, request: Request, owner: str = Depends(current_principal)
) -> list[RunOut]:
    """Every run of this team, newest first — including runs of revisions since replaced,
    which is what makes two of them comparable at all."""
    async with request.app.state.pool.acquire() as conn:
        team = await store.get_team(conn, team_id=team_id, owner_principal=owner)
        if team is None:
            raise HTTPException(404, detail="no such team")
        rows = await store.list_runs_for_team(conn, team_id=team_id, owner_principal=owner)
    return [RunOut.from_row(dict(row)) for row in rows]


@router.get("/runs/{run_id}")
async def get_run(run_id: int, request: Request, owner: str = Depends(current_principal)) -> RunOut:
    async with request.app.state.pool.acquire() as conn:
        row = await store.get_run(conn, run_id=run_id, owner_principal=owner)
    if row is None:
        raise HTTPException(404, detail="no such run")
    return RunOut.from_row(dict(row))


@router.get("/runs/{run_id}/steps")
async def get_run_steps(
    run_id: int, request: Request, owner: str = Depends(current_principal)
) -> list[RunStepOut]:
    """Who is waiting, who is working, who has finished and what they handed over — the
    same picture the progress stream carries, for a viewer that arrived late or came back
    (specs/teams-runs, "po ponownym otwarciu widać jego bieżący stan")."""
    async with request.app.state.pool.acquire() as conn:
        run = await store.get_run(conn, run_id=run_id, owner_principal=owner)
        if run is None:
            raise HTTPException(404, detail="no such run")
        rows = await store.get_run_steps(conn, run_id=run_id)
    return [RunStepOut.from_row(dict(row)) for row in rows]


@router.get("/runs/{run_id}/tool-calls")
async def get_run_tool_calls(
    run_id: int, request: Request, owner: str = Depends(current_principal)
) -> list[ToolCallOut]:
    async with request.app.state.pool.acquire() as conn:
        run = await store.get_run(conn, run_id=run_id, owner_principal=owner)
        if run is None:
            raise HTTPException(404, detail="no such run")
        rows = await store.get_run_tool_calls(conn, run_id=run_id)
    return [ToolCallOut.from_row(dict(row)) for row in rows]


@router.post("/runs/{run_id}/cancel", status_code=202)
async def cancel_run(
    run_id: int, request: Request, owner: str = Depends(current_principal)
) -> RunOut:
    """Asks a run to stop. 202, not 200: the status is written by the run itself as it
    unwinds, so what comes back here is the run as it was when the interruption was
    accepted — the operator's own view catches up through the stream or a reload."""
    async with request.app.state.pool.acquire() as conn:
        row = await store.get_run(conn, run_id=run_id, owner_principal=owner)
    if row is None:
        raise HTTPException(404, detail="no such run")
    if row["status"] not in ("pending", "running"):
        raise HTTPException(409, detail=f"the run is already {row['status']}")
    if not request.app.state.runs.cancel(run_id):
        # In the database as running, but nothing in this process is running it — the
        # state `store.fail_unfinished_runs` closes at start-up. Answering 409 rather than
        # pretending to interrupt something that is not there.
        raise HTTPException(409, detail="the run is not being worked on by this instance")
    return RunOut.from_row(dict(row))


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.get("/runs/{run_id}/events")
async def run_events(
    run_id: int, request: Request, owner: str = Depends(current_principal)
) -> StreamingResponse:
    """Progress as it happens, starting with where the run is now.

    The snapshot first, then live events: a viewer that opens halfway through has to see
    the agents that already finished, and one that reconnects must not have to guess what
    it missed. Dropping the connection unsubscribes a queue and nothing else — the run
    holds no reference to any of this (specs/teams-runs, "Zerwanie połączenia odbierającego
    postęp MUST NOT przerwać przebiegu").
    """
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        run = await store.get_run(conn, run_id=run_id, owner_principal=owner)
        if run is None:
            raise HTTPException(404, detail="no such run")
        steps = await store.get_run_steps(conn, run_id=run_id)

    registry = request.app.state.runs
    # Subscribed before the snapshot is sent, so an event landing between the two is
    # queued rather than lost.
    queue = registry.subscribe(run_id)
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
