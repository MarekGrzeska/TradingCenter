"""Pricing, running, reading and retrying a collection job."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
)

from ..contract import (
    EstimateRequest,
    JobEstimateOut,
    JobOut,
    JobPairViewOut,
    PairEstimateOut,
    Problem,
)
from ..errors import GatewayRefused
from ..jobs import (
    NothingToRetry,
    UnknownJob,
    estimate_job,
    list_jobs,
    read_job,
    retry_job,
)
from ..models import Resolution
from .deps import pool

router = APIRouter()


@router.post(
    "/jobs/estimate",
    tags=["jobs"],
    response_model=JobEstimateOut,
    summary="Price a collection job without creating it",
    description=(
        "Runs the exact planning a job creation would, without writing anything: no pair "
        "is tracked, no job exists afterwards. A symbol the gateway does not know comes "
        "back marked `unknown` rather than failing the whole estimate."
    ),
)
async def estimate_pairs(body: EstimateRequest, request: Request) -> JobEstimateOut:
    state = request.app.state
    now = datetime.now(UTC)

    known: list[tuple[str, Resolution]] = []
    unknown: dict[tuple[str, Resolution], PairEstimateOut] = {}
    for wanted in body.pairs:
        try:
            collectable = await state.instruments.is_collectable(wanted.symbol, wanted.resolution)
        except GatewayRefused:
            collectable = False
        if collectable:
            known.append((wanted.symbol, wanted.resolution))
        else:
            unknown[(wanted.symbol, wanted.resolution)] = PairEstimateOut.unknown_pair(
                wanted.symbol, wanted.resolution
            )

    async with state.pool.acquire() as conn:
        priced = await estimate_job(conn, known, body.collect_from, now)
    by_pair = {(p.symbol, p.resolution): PairEstimateOut.of(p) for p in priced.pairs}

    pairs_out = [
        by_pair.get((wanted.symbol, wanted.resolution))
        or unknown[(wanted.symbol, wanted.resolution)]
        for wanted in body.pairs
    ]
    return JobEstimateOut(
        pairs=pairs_out,
        total_estimated_candles=sum(p.estimated_candles for p in pairs_out),
        total_estimated_bytes=sum(p.estimated_bytes for p in pairs_out),
    )


@router.get(
    "/jobs",
    tags=["jobs"],
    response_model=list[JobPairViewOut],
    summary="Collection jobs, one row per pair they touched",
)
async def jobs(
    symbol: str | None = Query(None),
    resolution: Resolution | None = Query(None),
    db=Depends(pool),
) -> list[JobPairViewOut]:
    async with db.acquire() as conn:
        views = await list_jobs(conn, symbol, resolution)
    return [JobPairViewOut.of(view) for view in views]


@router.get(
    "/jobs/{job_id}",
    tags=["jobs"],
    response_model=JobOut,
    responses={404: {"model": Problem}},
    summary="One job, whole — every pair and every chunk it covers",
)
async def job(job_id: int, db=Depends(pool)) -> JobOut:
    async with db.acquire() as conn:
        found = await read_job(conn, job_id)
    if found is None:
        raise HTTPException(status_code=404, detail=f"no collection job with id {job_id}")
    return JobOut.of(found)


@router.post(
    "/jobs/{job_id}/retry",
    tags=["jobs"],
    response_model=JobOut,
    responses={404: {"model": Problem}, 409: {"model": Problem}},
    summary="Retry a job's failed or interrupted chunks",
    description=(
        "Resets only chunks left `failed` or `interrupted`, as a new attempt of the same "
        "job — never a new job, and never a chunk already `done`. Refused with 409 when "
        "there is nothing to retry."
    ),
)
async def retry(job_id: int, request: Request) -> JobOut:
    async with request.app.state.pool.acquire() as conn:
        try:
            retried = await retry_job(conn, job_id)
        except UnknownJob as err:
            raise HTTPException(status_code=404, detail=str(err)) from err
        except NothingToRetry as err:
            raise HTTPException(status_code=409, detail=str(err)) from err
    request.app.state.job_runner.notify()
    return JobOut.of(retried)
