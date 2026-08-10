"""Which pairs are collected, started and deleted — the operator's decisions."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
)

from ..contract import (
    FillOut,
    PairDeletionOut,
    Problem,
    TrackedPairOut,
    TrackedPairResult,
    TrackPairRequest,
    TrackPairsResult,
)
from ..coverage import clear_history_boundary, earliest_reachable
from ..deletion import close_for_deletion, delete_pair_data, read_deletions
from ..ingest import Ingest
from ..jobs import (
    FutureRequest,
    create_job,
    plan_chunks,
)
from ..models import Resolution
from ..tracking import (
    LimitReached,
    TrackedPair,
    TrackingRefused,
    add_pair,
    decide_late_pairs,
    read_status,
)
from .deps import pool

log = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/pairs",
    tags=["tracking"],
    response_model=list[TrackedPairOut],
    summary="Which pairs are collected, and whether collection is happening",
)
async def pairs(request: Request, db=Depends(pool)) -> list[TrackedPairOut]:
    moment = datetime.now(UTC)
    async with db.acquire() as conn:
        statuses = await read_status(conn, now=moment)

    decided = await decide_late_pairs(
        request.app.state.instruments, request.app.state.market_status, statuses, moment
    )
    ingest: Ingest = request.app.state.ingest

    return [
        TrackedPairOut(
            symbol=status.symbol,
            resolution=status.resolution,
            added_at=status.added_at,
            collect_from=status.collect_from,
            earliest_candle=status.earliest_candle,
            latest_candle=status.latest_candle,
            collection=collection,
            last_fill=FillOut.of(ingest.last_fill(status.symbol, status.resolution)),
        )
        for status, collection in decided
    ]

@router.post(
    "/pairs",
    tags=["tracking"],
    response_model=TrackPairsResult,
    status_code=201,
    responses={422: {"model": Problem}},
    summary="Start collecting one or more pairs",
    description=(
        "Each pair is validated against the gateway independently, so one refusal — an "
        "unknown symbol, the tracked-pairs ceiling — never withholds the pairs that were "
        "fine. Accepting at least one pair that needed history behind it starts a "
        "collection job and returns its id; a request whose pairs were all already fully "
        "covered accepts them with no job. The original single-pair shape (`symbol`, "
        "`resolution`) still works and still means the configured default depth."
    ),
)
async def track_pairs(body: TrackPairRequest, request: Request) -> TrackPairsResult:
    state = request.app.state
    now = datetime.now(UTC)

    # Refused here rather than left to `plan_chunks` below, which raises the same thing:
    # by then the pairs would already be tracked and ingest already resynced, so the
    # caller would get a refusal for a request that had nonetheless changed what the
    # archive collects. A refusal has to cost nothing.
    if body.collect_from is not None and body.collect_from > now:
        raise FutureRequest(
            f"{body.collect_from.isoformat()} is in the future; there is no history there"
        )

    results: list[TrackedPairResult] = []
    accepted: list[TrackedPair] = []
    first_refusal: tuple[int, str] | None = None
    for wanted in body.resolved_pairs():
        async with state.pool.acquire() as conn:
            try:
                pair = await add_pair(
                    conn,
                    state.instruments,
                    wanted.symbol,
                    wanted.resolution,
                    state.settings.max_tracked_pairs,
                    collect_from=body.collect_from,
                    default_bars=state.settings.default_backfill_bars,
                )
            except TrackingRefused as err:
                results.append(
                    TrackedPairResult(
                        symbol=wanted.symbol, resolution=wanted.resolution, refused=str(err)
                    )
                )
                if first_refusal is None:
                    status = 409 if isinstance(err, LimitReached) else 422
                    first_refusal = (status, str(err))
                continue
        accepted.append(pair)
        results.append(
            TrackedPairResult(
                symbol=pair.symbol, resolution=pair.resolution, pair=TrackedPairOut.of(pair)
            )
        )

    if not accepted:
        # Every pair was refused. A single-pair request — the shape every caller before
        # this change used — surfaces exactly the error it always did, rather than a 201
        # with the refusal buried in a list of one.
        status, detail = first_refusal or (422, "no pairs given")
        raise HTTPException(status_code=status, detail=detail)

    # Collection starts now rather than at the next restart.
    await state.ingest.sync()

    async with state.pool.acquire() as conn:
        plans = []
        for pair in accepted:
            # A request reaching deeper than the boundary the archive holds *is* the
            # instruction to measure it again, so the boundary goes first and the range is
            # planned whole. Only here: pricing a job writes nothing, and reading coverage
            # must not change what it reports (`market-data-store` spec, "Odczyt stanu
            # pokrycia nie zmienia granicy").
            #
            # Read from what this caller asked for, not from `pair.collect_from`. That one
            # is `LEAST(existing, new)` — the deepest moment this pair was *ever* asked to
            # reach — so re-adding a pair with no date at all, which asks for nothing new,
            # would look like a deeper request and drop a boundary nobody questioned.
            requested_from = body.collect_from
            if requested_from is not None:
                reachable = await earliest_reachable(conn, pair.symbol, pair.resolution)
                if reachable is not None and requested_from < reachable:
                    await clear_history_boundary(conn, pair.symbol, pair.resolution)
                    log.info(
                        "%s %s: asked for %s, below the recorded boundary %s — dropping it "
                        "and measuring again",
                        pair.symbol,
                        pair.resolution.value,
                        requested_from.isoformat(),
                        reachable.isoformat(),
                    )
            pair_plans, _ = await plan_chunks(
                conn, pair.symbol, pair.resolution, pair.collect_from, now
            )
            plans.extend(pair_plans)
        job = await create_job(conn, body.collect_from or now, plans)
    state.job_runner.notify()

    return TrackPairsResult(results=results, job_id=job.id)


@router.delete(
    "/pairs/{symbol}",
    tags=["tracking"],
    response_model=PairDeletionOut,
    responses={404: {"model": Problem}},
    summary="Stop collecting a pair and delete its data",
    description=(
        "Stops collection, releases the provider connection, and removes every candle "
        "and coverage range this pair holds — irreversibly. A symbol whose minute "
        "series is deleted also loses the rollups computed from it. 404 for a pair not "
        "currently tracked, which deletes nothing."
    ),
)
async def delete_pair(
    symbol: str, request: Request, resolution: Resolution = Query(Resolution.MINUTE)
) -> PairDeletionOut:
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        stopped = await close_for_deletion(conn, symbol, resolution)
    if stopped is None:
        raise HTTPException(
            status_code=404, detail=f"{symbol} {resolution.value} is not being collected"
        )

    # Between the two writes: the decision is already closed (nothing new claims this
    # pair's chunks, and `is_tracked` already reads false for it), so this is what
    # actually stops a live subscription — not a database write, and the reason the two
    # transactions in `close_for_deletion`/`delete_pair_data` cannot be one.
    await request.app.state.ingest.sync()

    async with pool.acquire() as conn:
        deletion = await delete_pair_data(conn, symbol, resolution)
    return PairDeletionOut.of(deletion)


@router.get(
    "/deletions",
    tags=["tracking"],
    response_model=list[PairDeletionOut],
    summary="Recorded deletions, newest first",
)
async def deletions(
    symbol: str | None = Query(None),
    resolution: Resolution | None = Query(None),
    db=Depends(pool),
) -> list[PairDeletionOut]:
    async with db.acquire() as conn:
        found = await read_deletions(conn, symbol, resolution)
    return [PairDeletionOut.of(deletion) for deletion in found]
