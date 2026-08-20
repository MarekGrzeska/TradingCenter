"""Sessions, their transcript, and the one route that starts a turn."""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from .. import store
from ..auth import PRINCIPAL_ID_HEADER, PRINCIPAL_NAME_HEADER, current_principal
from ..contract import (
    CreateSessionIn,
    MessageOut,
    PatchSessionIn,
    SendMessageIn,
    SessionOut,
    ToolCallOut,
)
from ..models_catalogue import ModelNotInCatalogue
from ..turn import Complete, Failed, Fragment, Stopped, ToolCalled, run_turn

log = logging.getLogger(__name__)

router = APIRouter()

# How often a silent stream gets a keep-alive comment. App Service drops a connection
# idle for 230s (design.md); well under half of that leaves room for a slow network hop
# on top of the timer itself.
_KEEPALIVE_SECONDS = 15


@router.post("/sessions", status_code=201)
async def create_session(
    body: CreateSessionIn, request: Request, owner: str = Depends(current_principal)
) -> SessionOut:
    try:
        model = request.app.state.agent.catalogue.resolve(body.model_id)
    except ModelNotInCatalogue as err:
        raise HTTPException(422, detail=str(err)) from err
    async with request.app.state.agent.pool.acquire() as conn:
        session = await store.create_session(conn, owner_principal=owner, model_id=model.id)
    return SessionOut.from_session(session)


@router.get("/sessions")
async def list_sessions(request: Request, owner: str = Depends(current_principal)) -> list[SessionOut]:
    async with request.app.state.agent.pool.acquire() as conn:
        sessions = await store.list_sessions(conn, owner_principal=owner)
    return [SessionOut.from_session(s) for s in sessions]


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: int, request: Request, owner: str = Depends(current_principal)
) -> SessionOut:
    async with request.app.state.agent.pool.acquire() as conn:
        session = await store.get_session(conn, session_id=session_id, owner_principal=owner)
    # A foreign session reads exactly like a missing one — specs/agent-browser-access,
    # "Odmowa dostępu do cudzej sesji MUST być nieodróżnialna od odpowiedzi o sesji
    # nieistniejącej".
    if session is None:
        raise HTTPException(404, detail="no such session")
    return SessionOut.from_session(session)


@router.get("/sessions/{session_id}/messages")
async def get_messages(
    session_id: int, request: Request, owner: str = Depends(current_principal)
) -> list[MessageOut]:
    async with request.app.state.agent.pool.acquire() as conn:
        session = await store.get_session(conn, session_id=session_id, owner_principal=owner)
        if session is None:
            raise HTTPException(404, detail="no such session")
        messages = await store.get_messages(conn, session_id=session_id)
        calls = await store.get_session_tool_calls(conn, session_id=session_id)
    return [MessageOut.from_message(m, calls.get(m.id, ())) for m in messages]


@router.get("/sessions/{session_id}/unclaimed-tool-calls")
async def get_unclaimed_tool_calls(
    session_id: int, request: Request, owner: str = Depends(current_principal)
) -> list[ToolCallOut]:
    """The calls in this session that no reply ever claimed — sent, and never answered for
    by a turn that reached its own end (specs/agent-trading).

    A route of its own rather than a field on the transcript above, and the reason is the
    transcript's shape: it publishes a list, so a field would mean publishing an object
    instead, and a terminal build from before that change calls `map` on it. The terminal
    is deployed separately from this module, so that window is real (design.md, D1).

    Empty for almost every session, and that is the point — a row here is the record of an
    order whose fate nobody knows.
    """
    async with request.app.state.agent.pool.acquire() as conn:
        session = await store.get_session(conn, session_id=session_id, owner_principal=owner)
        if session is None:
            raise HTTPException(404, detail="no such session")
        calls = await store.get_session_orphan_tool_calls(conn, session_id=session_id)
    return [ToolCallOut.from_tool_call(call) for call in calls]


@router.patch("/sessions/{session_id}")
async def patch_session(
    session_id: int, body: PatchSessionIn, request: Request, owner: str = Depends(current_principal)
) -> SessionOut:
    if body.model_id is not None:
        try:
            request.app.state.agent.catalogue.get(body.model_id)
        except ModelNotInCatalogue as err:
            raise HTTPException(422, detail=str(err)) from err

    async with request.app.state.agent.pool.acquire() as conn:
        session = await store.get_session(conn, session_id=session_id, owner_principal=owner)
        if session is None:
            raise HTTPException(404, detail="no such session")
        # Both edits go through their own statement rather than one built by hand from
        # whichever fields arrived — two small UPDATEs on a single-operator table cost
        # nothing, and a query assembled from a request body is the shape SQL injection
        # arrives in.
        if body.model_id is not None:
            session = await store.set_session_model(
                conn, session_id=session_id, owner_principal=owner, model_id=body.model_id
            )
        if body.title is not None:
            session = await store.set_session_title(
                conn, session_id=session_id, owner_principal=owner, title=body.title
            )
    if session is None:
        raise HTTPException(404, detail="no such session")
    return SessionOut.from_session(session)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: int, request: Request, owner: str = Depends(current_principal)
) -> None:
    """Removes the rozmowa from the operator's history. What it cost stays in the ledger —
    see `store.delete_session` for why that is not a compromise but the point."""
    async with request.app.state.agent.pool.acquire() as conn:
        removed = await store.delete_session(conn, session_id=session_id, owner_principal=owner)
    if not removed:
        raise HTTPException(404, detail="no such session")


def _operator_principal(request: Request) -> str | None:
    """Who this turn acts for, as the authenticator in front of this process said it.

    Not the bearer token, which is what travelled here while the team tools stood in their
    own process: a token needs a validator, and there is none between this line and the
    routes it ends up at. The principal has already been through one — Easy Auth wrote
    these headers and overwrote whatever the caller sent — so it is the identity itself
    that is carried, for the length of a turn and never written down.

    `None` where nothing authenticates, which is a developer's machine: the team tools then
    act carrying no identity at all, and what they create belongs to the same principal the
    local terminal gets (`teams_tools/operator.py`).
    """
    identity = (
        request.headers.get(PRINCIPAL_ID_HEADER) or request.headers.get(PRINCIPAL_NAME_HEADER) or ""
    ).strip()
    return identity or None


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: int, body: SendMessageIn, request: Request, owner: str = Depends(current_principal)
) -> StreamingResponse:
    pool = request.app.state.agent.pool
    async with pool.acquire() as conn:
        session = await store.get_session(conn, session_id=session_id, owner_principal=owner)
        if session is None:
            raise HTTPException(404, detail="no such session")
        # Written before the model is ever called — specs/agent-chat, "Wypowiedź
        # operatora MUST być zapisana zanim moduł zawoła model": what the operator
        # typed survives a call that never answers.
        await store.append_operator_message(conn, session_id=session_id, content=body.content)

    model_entry = request.app.state.agent.catalogue.get(session.current_model_id)
    queue: asyncio.Queue = asyncio.Queue()
    # Set by the stop route, asked by the graph between one fragment and the next. Created
    # here rather than in `run_turn` so the route below has something to find before the
    # turn has read its first chunk.
    stop = asyncio.Event()

    task = asyncio.create_task(
        run_turn(
            pool,
            session_id=session_id,
            model_entry=model_entry,
            provider=request.app.state.agent.provider,
            queue=queue,
            tool_server=request.app.state.agent.tool_server,
            chart=body.chart.to_snapshot() if body.chart is not None else None,
            # The operator's own identity, taken off the request being served and carried
            # no further than the tool sources that act in their name. Tools that create
            # teams and spend money must belong to the person asking, not to this process.
            # Absent — local development, where nothing authenticates — those tools act
            # carrying no identity rather than refusing, because refusing there would take
            # the whole surface away from a desk.
            operator_principal=_operator_principal(request),
            stop=stop,
        )
    )
    # A task with nothing referencing it is eligible for collection mid-run — kept here
    # so it always finishes, whether or not the stream below is still being read
    # (design.md, "Tura modelu przeżywa rozłączenie wołającego").
    background = request.app.state.agent.background_tasks
    background.add(task)
    task.add_done_callback(background.discard)

    # Findable by rozmowa for as long as it runs. A second turn in the same rozmowa cannot
    # start while one is in flight — the terminal disables sending, and a caller that does
    # it anyway replaces the entry, which is the honest answer: stop then ends the turn
    # that is actually running.
    running = request.app.state.agent.running_turns
    running[session_id] = stop
    task.add_done_callback(lambda _: running.pop(session_id, None))

    def _close_stream_if_the_turn_died(finished: asyncio.Task) -> None:
        """A turn that raises before its own guard leaves nothing on the queue, and the
        stream below then waits for an event that will never come — a hang rather than an
        error, held open by keep-alives until the client gives up.

        `run_turn` guards the model call itself, but everything before it — reading the
        prompt, asking the tool servers what they publish — is outside that guard, and
        this is what covers it. Found by a tool server whose stub had the wrong signature;
        the bug it exposed is older than that change.
        """
        if finished.cancelled() or finished.exception() is None:
            return
        log.exception(
            "the turn task failed before it could report anything",
            exc_info=finished.exception(),
        )
        queue.put_nowait(Failed("the turn failed before it could answer"))

    task.add_done_callback(_close_stream_if_the_turn_died)

    async def event_stream():
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=_KEEPALIVE_SECONDS)
            except TimeoutError:
                yield ": ping\n\n"
                continue
            if isinstance(event, Fragment):
                yield _sse("fragment", {"text": event.text})
            elif isinstance(event, ToolCalled):
                # The same shape the transcript publishes for this call once it has a
                # row, built from the same contract model — a caller that keeps what the
                # stream gave it and a caller that reloads afterwards MUST end up holding
                # the same thing (specs/agent-chat, "Wywołanie narzędzia dociera w
                # trakcie tury").
                published = ToolCallOut.from_recorded(event.call, event.position)
                yield _sse("tool_call", published.model_dump(mode="json"))
            elif isinstance(event, Complete):
                yield _sse("complete", {"incomplete": event.incomplete})
                return
            elif isinstance(event, Failed):
                yield _sse("error", {"message": event.message})
                return
            elif isinstance(event, Stopped):
                # No payload: what there is to say is that the operator ended it, and the
                # reply itself arrives from the transcript like every other reply
                # (specs/agent-chat, "Operator zatrzymuje turę w trakcie").
                yield _sse("stopped", {})
                return

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/sessions/{session_id}/stop", status_code=204)
async def stop_turn(
    session_id: int, request: Request, owner: str = Depends(current_principal)
) -> None:
    """Ends the turn running in this rozmowa, at the next boundary the graph reaches.

    `204` whether or not one was running. A stop arriving a moment after the turn wrote
    its last fragment is a race, not a mistake — and there is nothing an operator could do
    with an error saying they were too late (design.md, D1).

    The rozmowa is read first, with the owner filter every other route here uses, so a
    stranger's session and a session that does not exist answer the same `404`. Without
    that read, the registry alone would tell a stranger whether somebody else's rozmowa is
    busy right now.
    """
    async with request.app.state.agent.pool.acquire() as conn:
        session = await store.get_session(conn, session_id=session_id, owner_principal=owner)
    if session is None:
        raise HTTPException(404, detail="no such session")

    stop = request.app.state.agent.running_turns.get(session_id)
    if stop is not None:
        stop.set()
