"""Strategies and their revisions: checked when saved, never changed after, archived rather than deleted."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query

from .. import documents, store
from ..archive import ArchiveUnavailable
from ..contract import (
    ProblemsOut,
    RevisionOut,
    SavedOut,
    StrategyDetailOut,
    StrategyOut,
    ValidationOut,
)
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
    return RevisionOut.model_validate(r.__dict__)


@router.post("/validate", response_model=ValidationOut, responses={503: {"description": "the archive did not answer"}})
async def validate(raw: dict[str, Any] = _DOCUMENT, reading=Depends(archive)) -> ValidationOut:
    """Exactly what saving would answer, and nothing saved."""
    checked, problems = await _checked(raw, reading)
    return ValidationOut.model_validate({"valid": checked is not None, "problems": [p.as_dict() for p in problems]})


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
    responses={404: {}, 422: {"model": ProblemsOut}, 503: {"description": "the archive did not answer"}},
)
async def save_revision(strategy_id: int = ID, raw: dict[str, Any] = _DOCUMENT, db=Depends(pool), reading=Depends(archive)):
    checked, problems = await _checked(raw, reading)
    if checked is None:
        return refused("the document is not a valid strategy", problems)
    try:
        saved = await store.save_revision(db, strategy_id, checked, "operator")
    except store.NotFound:
        raise not_found(f"strategy {strategy_id}") from None
    return SavedOut(strategy_id=saved.strategy_id, revision=saved.revision, created=saved.created)


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


async def _set_archived(db, strategy_id: int, archived: bool) -> StrategyOut:
    async with db.acquire() as conn:
        try:
            return _summary(await store.set_archived(conn, strategy_id, archived))
        except store.NotFound:
            raise not_found(f"strategy {strategy_id}") from None
