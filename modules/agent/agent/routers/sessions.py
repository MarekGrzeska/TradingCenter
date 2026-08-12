"""Sessions, their transcript, and the one route that starts a turn."""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from .. import store
from ..auth import current_principal
from ..contract import CreateSessionIn, MessageOut, PatchSessionIn, SendMessageIn, SessionOut
from ..models_catalogue import ModelNotInCatalogue
from ..turn import Complete, Failed, Fragment, run_turn

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
    return [MessageOut.from_message(m) for m in messages]


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
        )
    )
    # A task with nothing referencing it is eligible for collection mid-run — kept here
    # so it always finishes, whether or not the stream below is still being read
    # (design.md, "Tura modelu przeżywa rozłączenie wołającego").
    background = request.app.state.background_tasks
    background.add(task)
    task.add_done_callback(background.discard)

    async def event_stream():
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=_KEEPALIVE_SECONDS)
            except TimeoutError:
                yield ": ping\n\n"
                continue
            if isinstance(event, Fragment):
                yield _sse("fragment", {"text": event.text})
            elif isinstance(event, Complete):
                yield _sse("complete", {"incomplete": event.incomplete})
                return
            elif isinstance(event, Failed):
                yield _sse("error", {"message": event.message})
                return

    return StreamingResponse(event_stream(), media_type="text/event-stream")
