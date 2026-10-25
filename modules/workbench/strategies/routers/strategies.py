"""Strategies and their revisions: checked when saved, never changed after, archived rather than deleted."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from fastapi.responses import JSONResponse

from .. import changes, documents, drafts, store
from ..archive import ArchiveUnavailable
from ..contract import (
    ChangesOut,
    ConflictOut,
    ConversationIn,
    DraftOut,
    ProblemsOut,
    RevisionEntryOut,
    RevisionOut,
    SavedOut,
    StrategyDetailOut,
    StrategyOut,
    ValidationOut,
)
from ..document import execution, execution_of
from ..summary import summarize
from .deps import BIGINT, INTEGER, archive, not_found, pool, refused

router = APIRouter(tags=["strategies"])

_DOCUMENT = Body(..., description="a strategy document — its shape is `GET /language`")
ID = Path(ge=1, le=BIGINT)


async def _checked(raw: dict[str, Any], reading):
    try:
        return await documents.check(raw, reading)
    except ArchiveUnavailable as err:
        # Never checked without the archive: a symbol nobody could verify is not a valid one.
        raise HTTPException(status_code=503, detail=f"the document cannot be checked now: {err}") from err


def _summary(s: store.Summary) -> StrategyOut:
    return StrategyOut.model_validate(s.__dict__)


def _revision(r: store.Revision) -> RevisionOut:
    return RevisionOut.model_validate(r.__dict__ | {"summary": summarize(r.document), "execution": execution_of(r.document)})


def conflict(latest: int) -> JSONResponse:
    body = ConflictOut(
        detail=f"revision {latest} was saved after the one this change was made to; read it before saving",
        latest_revision=latest,
    )
    return JSONResponse(status_code=409, content=body.model_dump())


@router.post("/validate", response_model=ValidationOut, responses={503: {"description": "the archive did not answer"}})
async def validate(raw: dict[str, Any] = _DOCUMENT, reading=Depends(archive)) -> ValidationOut:
    """Exactly what saving would answer, and nothing saved."""
    checked, problems = await _checked(raw, reading)
    return ValidationOut.model_validate({
        "valid": checked is not None,
        "problems": [p.as_dict() for p in problems],
        "summary": None if checked is None else summarize(checked.canonical),
        "execution": None if checked is None else execution(checked.document),
    })


@router.get("/strategies", response_model=list[StrategyOut])
async def list_strategies(archived: bool = Query(False, description="list only the archived ones"), db=Depends(pool)):
    async with db.acquire() as conn:
        return [_summary(s) for s in await store.list_strategies(conn, archived=archived)]


@router.post(
    "/strategies", response_model=SavedOut, status_code=201,
    responses={422: {"model": ProblemsOut}, 503: {"description": "the archive did not answer"}},
)
async def create(raw: dict[str, Any] = _DOCUMENT, db=Depends(pool), reading=Depends(archive)):
    checked, problems = await _checked(raw, reading)
    if checked is None:
        return refused("the document is not a valid strategy", problems)
    saved = await store.create(db, checked, "operator")
    return SavedOut(strategy_id=saved.strategy_id, revision=saved.revision, created=saved.created)


@router.get("/strategies/{strategy_id}", response_model=StrategyDetailOut, responses={404: {}})
async def detail(strategy_id: int = ID, db=Depends(pool)) -> StrategyDetailOut:
    # One snapshot for both reads, so a revision saved in between cannot pair one revision's summary with another's body.
    async with db.acquire() as conn, conn.transaction(isolation="repeatable_read", readonly=True):
        try:
            summary = await store.get_strategy(conn, strategy_id)
            revision = await store.get_revision(conn, strategy_id)
        except store.NotFound:
            raise not_found(f"strategy {strategy_id}") from None
    return StrategyDetailOut.model_validate(summary.__dict__ | {"revision": _revision(revision)})


@router.post(
    "/strategies/{strategy_id}/revisions", response_model=SavedOut,
    responses={
        404: {}, 409: {"model": ConflictOut}, 422: {"model": ProblemsOut},
        503: {"description": "the archive did not answer"},
    },
)
async def save_revision(
    strategy_id: int = ID,
    raw: dict[str, Any] = _DOCUMENT,
    based_on: int | None = Query(
        None, ge=1, le=INTEGER, description="the revision this change was made to; a later one is a 409"
    ),
    db=Depends(pool),
    reading=Depends(archive),
):
    checked, problems = await _checked(raw, reading)
    if checked is None:
        return refused("the document is not a valid strategy", problems)
    try:
        saved = await store.save_revision(db, strategy_id, checked, "operator", based_on)
    except store.NotFound:
        raise not_found(f"strategy {strategy_id}") from None
    except store.Conflict as err:
        return conflict(err.latest)
    return SavedOut(strategy_id=saved.strategy_id, revision=saved.revision, created=saved.created)


@router.get("/strategies/{strategy_id}/revisions", response_model=list[RevisionEntryOut], responses={404: {}})
async def revisions(strategy_id: int = ID, db=Depends(pool)) -> list[RevisionEntryOut]:
    """Newest first, without the documents."""
    async with db.acquire() as conn:
        try:
            return [RevisionEntryOut.model_validate(e.__dict__) for e in await store.list_revisions(conn, strategy_id)]
        except store.NotFound:
            raise not_found(f"strategy {strategy_id}") from None


@router.get("/strategies/{strategy_id}/revisions/{n}/changes", response_model=ChangesOut, responses={404: {}})
async def revision_changes(
    strategy_id: int = ID,
    n: int = Path(ge=1, le=INTEGER),
    against: int | None = Query(None, ge=1, le=INTEGER, description="the revision to compare with; the previous one if left out"),
    db=Depends(pool),
) -> ChangesOut:
    other = against if against is not None else (n - 1 if n > 1 else None)
    async with db.acquire() as conn:
        try:
            revision = await store.get_revision(conn, strategy_id, n)
            base = None if other is None else await store.get_revision(conn, strategy_id, other)
        except store.NotFound:
            raise not_found(f"revision {n} or {other} of strategy {strategy_id}") from None
    found = [] if base is None else [c.as_dict() for c in changes.between(base.document, revision.document)]
    return ChangesOut.model_validate({"strategy_id": strategy_id, "n": n, "against": other, "changes": found})


@router.get("/strategies/{strategy_id}/revisions/{n}", response_model=RevisionOut, responses={404: {}})
async def revision(strategy_id: int = ID, n: int = Path(ge=1, le=INTEGER), db=Depends(pool)) -> RevisionOut:
    async with db.acquire() as conn:
        try:
            return _revision(await store.get_revision(conn, strategy_id, n))
        except store.NotFound:
            raise not_found(f"revision {n} of strategy {strategy_id}") from None


@router.post("/strategies/{strategy_id}/archive", response_model=StrategyOut, responses={404: {}})
async def archive_strategy(strategy_id: int = ID, db=Depends(pool)) -> StrategyOut:
    return await _set_archived(db, strategy_id, True)


@router.post("/strategies/{strategy_id}/restore", response_model=StrategyOut, responses={404: {}})
async def restore_strategy(strategy_id: int = ID, db=Depends(pool)) -> StrategyOut:
    return await _set_archived(db, strategy_id, False)


@router.put("/strategies/{strategy_id}/conversation", response_model=StrategyOut, responses={404: {}})
async def set_conversation(body: ConversationIn, strategy_id: int = ID, db=Depends(pool)) -> StrategyOut:
    """The conversation the strategy's window reopens. Neither a revision nor a trial; the id is not checked."""
    async with db.acquire() as conn:
        try:
            return _summary(await store.set_conversation(conn, strategy_id, body.conversation_id))
        except store.NotFound:
            raise not_found(f"strategy {strategy_id}") from None


@router.get("/strategies/{strategy_id}/draft", response_model=DraftOut, responses={404: {}})
async def draft(strategy_id: int = ID, db=Depends(pool)) -> DraftOut:
    """The agent's draft of this strategy, not saved as a revision; 404 when there is none."""
    return await _draft(db, strategy_id)


@router.delete("/strategies/{strategy_id}/draft", status_code=204)
async def discard_draft(strategy_id: int = ID, db=Depends(pool)) -> None:
    async with db.acquire() as conn:
        await drafts.discard(conn, strategy_id)


@router.get("/drafts/new", response_model=DraftOut, responses={404: {}})
async def new_draft(db=Depends(pool)) -> DraftOut:
    """The agent's draft of a strategy not saved yet; 404 when there is none."""
    return await _draft(db, None)


@router.delete("/drafts/new", status_code=204)
async def discard_new_draft(db=Depends(pool)) -> None:
    async with db.acquire() as conn:
        await drafts.discard(conn, None)


async def _draft(db, strategy_id: int | None) -> DraftOut:
    async with db.acquire() as conn:
        found = await drafts.get(conn, strategy_id)
    if found is None:
        raise not_found("a draft" if strategy_id is None else f"a draft of strategy {strategy_id}")
    return DraftOut.model_validate(found.__dict__)


async def _set_archived(db, strategy_id: int, archived: bool) -> StrategyOut:
    async with db.acquire() as conn:
        try:
            return _summary(await store.set_archived(conn, strategy_id, archived))
        except store.NotFound:
            raise not_found(f"strategy {strategy_id}") from None
