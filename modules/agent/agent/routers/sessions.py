"""Sessions, their transcript, and the one route that starts a turn."""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from .. import store
from ..auth import current_principal
from ..contract import (
    CreateSessionIn,
    MessageOut,
    PatchSessionIn,
    SendMessageIn,
    SessionOut,
    ToolCallOut,
)
from ..models_catalogue import ModelNotInCatalogue
from ..turn import Complete, Failed, Fragment, ToolCalled, run_turn

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
        model = request.app.state.catalogue.resolve(body.model_id)
    except ModelNotInCatalogue as err:
        raise HTTPException(422, detail=str(err)) from err
    async with request.app.state.pool.acquire() as conn:
        session = await store.create_session(conn, owner_principal=owner, model_id=model.id)
    return SessionOut.from_session(session)


@router.get("/sessions")
async def list_sessions(request: Request, owner: str = Depends(current_principal)) -> list[SessionOut]:
    async with request.app.state.pool.acquire() as conn:
        sessions = await store.list_sessions(conn, owner_principal=owner)
    return [SessionOut.from_session(s) for s in sessions]


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: int, request: Request, owner: str = Depends(current_principal)
) -> SessionOut:
    async with request.app.state.pool.acquire() as conn:
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
    async with request.app.state.pool.acquire() as conn:
        session = await store.get_session(conn, session_id=session_id, owner_principal=owner)
        if session is None:
            raise HTTPException(404, detail="no such session")
        messages = await store.get_messages(conn, session_id=session_id)
        calls = await store.get_session_tool_calls(conn, session_id=session_id)
    return [MessageOut.from_message(m, calls.get(m.id, ())) for m in messages]


@router.patch("/sessions/{session_id}")
async def patch_session(
    session_id: int, body: PatchSessionIn, request: Request, owner: str = Depends(current_principal)
) -> SessionOut:
    if body.model_id is not None:
        try:
            request.app.state.catalogue.get(body.model_id)
        except ModelNotInCatalogue as err:
            raise HTTPException(422, detail=str(err)) from err

    async with request.app.state.pool.acquire() as conn:
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
    async with request.app.state.pool.acquire() as conn:
        removed = await store.delete_session(conn, session_id=session_id, owner_principal=owner)
    if not removed:
        raise HTTPException(404, detail="no such session")


def _bearer(request: Request) -> str | None:
    """The caller's own token, as presented. Easy Auth validates it and leaves it in
    place, so this is the same credential the terminal holds — not a copy this module
    minted and not one it may keep: it is passed on for the length of a turn and never
    written down."""
    header = request.headers.get("authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: int, body: SendMessageIn, request: Request, owner: str = Depends(current_principal)
) -> StreamingResponse:
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        session = await store.get_session(conn, session_id=session_id, owner_principal=owner)
        if session is None:
            raise HTTPException(404, detail="no such session")
        # Written before the model is ever called — specs/agent-chat, "Wypowiedź
        # operatora MUST być zapisana zanim moduł zawoła model": what the operator
        # typed survives a call that never answers.
        await store.append_operator_message(conn, session_id=session_id, content=body.content)

    model_entry = request.app.state.catalogue.get(session.current_model_id)
    queue: asyncio.Queue = asyncio.Queue()

    task = asyncio.create_task(
        run_turn(
            pool,
            session_id=session_id,
            model_entry=model_entry,
            provider=request.app.state.provider,
            queue=queue,
            tool_server=request.app.state.tool_server,
            chart=body.chart.to_snapshot() if body.chart is not None else None,
            # The operator's own credential, taken off the request being served and
            # carried no further than the tool servers that act in their name. Tools
            # that create teams and spend money must belong to the person asking, not to
            # this module (design.md of add-teams-mcp, D2). Absent — local development,
            # where nothing authenticates — those tools refuse and say why.
            operator_token=_bearer(request),
        )
    )
    # A task with nothing referencing it is eligible for collection mid-run — kept here
    # so it always finishes, whether or not the stream below is still being read
    # (design.md, "Tura modelu przeżywa rozłączenie wołającego").
    background = request.app.state.background_tasks
    background.add(task)
    task.add_done_callback(background.discard)

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

    return StreamingResponse(event_stream(), media_type="text/event-stream")
