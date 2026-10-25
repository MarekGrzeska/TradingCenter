"""Runs: queued at once, computed in the background, cancelled on request."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query

from .. import runs, store
from ..contract import (
    ProblemsOut,
    RunAcceptedOut,
    RunCancelledOut,
    RunOut,
    RunSummaryOut,
    TradesPageOut,
)
from ..runs import RunIn
from .deps import BIGINT, not_found, pool, queue, refused, settings

router = APIRouter(tags=["runs"])


@router.post(
    "/runs", response_model=RunAcceptedOut, status_code=202,
    responses={404: {"description": "no such strategy or revision"}, 422: {"model": ProblemsOut}},
)
async def enqueue(body: RunIn, db=Depends(pool), run_queue=Depends(queue), config=Depends(settings)):
    """Checked against the revision's parameters and the run's ceiling, then queued — never computed in the request."""
    async with db.acquire() as conn:
        try:
            revision = await store.get_revision(conn, body.strategy_id, body.revision)
        except store.NotFound:
            raise not_found("that strategy or revision") from None
        declared = revision.document.get("params", {})
        problems = runs.check_request(body, declared, config.max_minute_bars)
        if problems:
            return refused("the run cannot be queued", problems)
        params = runs.resolved_params(body, declared)
        run_id = await runs.enqueue(conn, body, revision.n, params)
    run_queue.wake()
    return RunAcceptedOut(id=run_id, strategy_id=body.strategy_id, revision=revision.n, status="queued")


@router.post("/runs/{run_id}/cancel", response_model=RunCancelledOut, responses={404: {"description": "no such run"}})
async def cancel(run_id: int = Path(ge=1, le=BIGINT), db=Depends(pool)) -> RunCancelledOut:
    async with db.acquire() as conn:
        was = await runs.cancel(conn, run_id)
        if was is None:
            raise not_found(f"run {run_id}")
        now = await runs.status_of(conn, run_id)
    return RunCancelledOut.model_validate({"id": run_id, "status": now, "was": was})


@router.get("/runs", response_model=list[RunSummaryOut])
async def list_runs(
    strategy_id: int | None = Query(None, ge=1, le=BIGINT, description="only this strategy's runs"),
    offset: int = Query(0, ge=0, le=BIGINT),
    limit: int = Query(100, ge=1, le=500),
    db=Depends(pool),
) -> list[RunSummaryOut]:
    """Newest first, a page at a time, without reports (`GET /runs/{id}` has one). Failed and cancelled runs are listed
    too; the strategy's `trials` counts the finished ones."""
    async with db.acquire() as conn:
        rows = await runs.list_runs(conn, strategy_id, offset, limit)
    return [
        RunSummaryOut.model_validate(
            dict(row) | {"request": store.decoded(row["request"]), "headline": store.decoded(row["headline"])}
        )
        for row in rows
    ]


@router.get("/runs/{run_id}", response_model=RunOut, responses={404: {"description": "no such run"}})
async def detail(run_id: int = Path(ge=1, le=BIGINT), db=Depends(pool)) -> RunOut:
    async with db.acquire() as conn:
        row = await runs.get_run(conn, run_id)
    if row is None:
        raise not_found(f"run {run_id}")
    return RunOut.model_validate(row.__dict__)


@router.get("/runs/{run_id}/trades", response_model=TradesPageOut, responses={404: {"description": "no such run"}})
async def trades(
    run_id: int = Path(ge=1, le=BIGINT),
    offset: int = Query(0, ge=0, le=BIGINT),
    limit: int = Query(200, ge=1, le=1000),
    db=Depends(pool),
) -> TradesPageOut:
    async with db.acquire() as conn:
        if await runs.status_of(conn, run_id) is None:
            raise not_found(f"run {run_id}")
        total, rows = await runs.trades_page(conn, run_id, offset, limit)
    return TradesPageOut.model_validate({
        "run_id": run_id, "total": total,
        "trades": [dict(row) | {"costs": store.decoded(row["costs"])} for row in rows],
    })
