"""Runs: queued at once, computed in the background, cancelled on request."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import Field

from .. import compare, runs, store
from ..archive import ArchiveUnavailable
from ..broker_costs import BrokerCostsMissing
from ..contract import (
    ComparisonOut,
    ProblemsOut,
    RunAcceptedOut,
    RunCancelledOut,
    RunOut,
    RunSummaryOut,
    TradesPageOut,
)
from ..problems import Problem
from ..runs import RunIn
from .deps import BIGINT, archive, not_found, pool, queue, refused, settings

router = APIRouter(tags=["runs"])


@router.post(
    "/runs", response_model=RunAcceptedOut, status_code=202,
    responses={
        404: {"description": "no such strategy or revision"}, 422: {"model": ProblemsOut},
        503: {"description": "the run needs the broker's costs and the archive could not ask for them"},
    },
)
async def enqueue(
    body: RunIn, db=Depends(pool), run_queue=Depends(queue), config=Depends(settings), reading=Depends(archive)
):
    """Checked against the revision's parameters and the run's ceiling, then queued — never computed in the request.
    Without `costs` the instrument's profile is used, read off the broker the first time."""
    async with db.acquire() as conn:
        try:
            revision = await store.get_revision(conn, body.strategy_id, body.revision)
        except store.NotFound:
            raise not_found("that strategy or revision") from None
        declared = revision.document.get("params", {})
        problems = runs.check_request(body, declared, config.max_minute_bars)
        if problems:
            return refused("the run cannot be queued", problems)
        try:
            costs = await runs.resolved_costs(conn, reading, body, revision.document["symbol"])
        except BrokerCostsMissing as err:
            return refused("the broker's costs are incomplete; nothing was queued", [Problem("costs", str(err))])
        except ArchiveUnavailable as err:
            raise HTTPException(status_code=503, detail=f"the broker's costs cannot be read now: {err}") from err
        params = runs.resolved_params(body, declared)
        run_id = await runs.enqueue(conn, body, revision.n, params, costs)
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
    return [_summary(row) for row in rows]


def _summary(row) -> RunSummaryOut:
    request, headline = store.decoded(row["request"]), store.decoded(row["headline"])
    if headline is not None:
        marks = runs.costs_marks(request, row["requested_by"])
        headline = headline | {"costs_source": marks["costs_source"], "without_costs": marks["without_costs"]}
    return RunSummaryOut.model_validate(dict(row) | {"request": request, "headline": headline})


# Before `/runs/{run_id}`: routes match in order, and `compare` would otherwise reach it as a run id that is not a number.
@router.get(
    "/runs/compare", response_model=ComparisonOut,
    responses={404: {"description": "no such run"}, 422: {"model": ProblemsOut}},
)
async def compare_runs(
    run_ids: list[Annotated[int, Field(ge=1, le=BIGINT)]] = Query(alias="run_id", description="2 to 5 different finished runs, in the order to show them"),
    db=Depends(pool),
):
    """The same rule as the agent's `compare_runs`: refused, with every difference named, unless the runs share the
    range, the costs and the engine version."""
    if (problem := compare.count_problem(run_ids)) is not None:
        return refused("these runs cannot be compared", [Problem("run_id", problem)])
    async with db.acquire() as conn:
        rows = [await runs.get_run(conn, run_id) for run_id in run_ids]
    missing = [str(run_id) for run_id, row in zip(run_ids, rows, strict=True) if row is None]
    if missing:
        raise not_found(f"run {', '.join(missing)}")
    try:
        compared = compare.compare([row for row in rows if row is not None])
    except compare.NotComparable as err:
        return refused("these runs cannot be compared", [Problem("run_id", reason) for reason in err.reasons])
    return ComparisonOut.model_validate({"runs": compared})


@router.get("/runs/{run_id}", response_model=RunOut, responses={404: {"description": "no such run"}})
async def detail(run_id: int = Path(ge=1, le=BIGINT), db=Depends(pool)) -> RunOut:
    async with db.acquire() as conn:
        row = await runs.get_run(conn, run_id)
    if row is None:
        raise not_found(f"run {run_id}")
    report = None if row.report is None else row.report | runs.costs_marks(row.request, row.requested_by)
    return RunOut.model_validate(row.__dict__ | {"report": report})


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
