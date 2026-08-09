"""The published surface: FastAPI over the archive, plus the subscription.

The one thing worth reading twice is `/ws/candles`. Its first message is a snapshot and
every message after it is a change, and the two are joined here rather than by whoever is
consuming them. That is the whole reason the seam stopped being the terminal's problem:
the snapshot is read while the room is held still and the subscriber attaches before it is
released, so no candle can fall between them and none can arrive twice.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from .config import Settings
from .contract import (
    CandleOut,
    CandlesOut,
    CoverageOut,
    EstimateRequest,
    FillOut,
    JobEstimateOut,
    JobOut,
    JobPairViewOut,
    PairCoverageOut,
    PairDeletionOut,
    PairEstimateOut,
    Problem,
    TrackedPairOut,
    TrackedPairResult,
    TrackPairRequest,
    TrackPairsResult,
    Uncovered,
)
from .coverage import earliest_reachable, read_coverage, uncovered_within
from .db import pool as make_pool
from .deletion import close_for_deletion, delete_pair_data, read_deletions
from .errors import GatewayError, GatewayRefused, GatewayUnreachable
from .gateway import GatewayHistory, GatewayInstruments, http_client
from .hub import Hub
from .ingest import Ingest
from .ingest.live import store_closed_candle
from .jobs import (
    FutureRequest,
    JobRunner,
    NothingToRetry,
    UnknownJob,
    create_job,
    estimate_job,
    interrupt_orphaned_chunks,
    list_jobs,
    plan_chunks,
    read_job,
    retry_job,
)
from .models import Candle, PriceSide, Resolution
from .rollups import DERIVABLE, read_derived
from .store import read_candles, read_recent
from .tracking import (
    CollectionState,
    LimitReached,
    TrackedPair,
    TrackingRefused,
    add_pair,
    collection_state,
    is_tracked,
    read_status,
)

log = logging.getLogger(__name__)

# How many settled candles a new subscriber is handed before the changes start. Enough for
# a chart to draw something immediately; a consumer wanting more asks the range endpoint,
# which is what it is for.
SNAPSHOT_CANDLES = 500

DERIVED_NOTE = (
    "Resolutions between MINUTE_5 and HOUR_4 are computed from the minute series rather "
    "than collected separately — the provider serves 1000 candles per request at ten "
    "requests a second, so fetching each one costs its own traffic for data the finest "
    "already implies. MINUTE, DAY and WEEK come from the provider: a daily boundary "
    "follows the venue's session, not the clock."
)


def candle_sink(pool, hub: Hub):
    """Where ingest sends every candle it sees, forming or closed.

    The storing happens inside the hub's hold rather than before it. That is the one thing
    that makes a snapshot airtight: a write committing outside the hold can land between a
    subscriber's snapshot query and its attachment, and the same period then arrives twice
    — once in the snapshot and once as a change.

    A forming candle is published and not stored. It changes with every quote and
    understates its own range until the period closes, but a chart that never saw it would
    be missing the bar the price is actually in.
    """

    async def sink(candle: Candle) -> None:
        if candle.forming:
            await hub.publish(candle.symbol, candle.resolution, candle)
            return

        async def store() -> None:
            await store_closed_candle(pool, candle)

        await hub.publish(candle.symbol, candle.resolution, candle, store=store)

    return sink


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()  # type: ignore[call-arg]

    async with make_pool(settings.database_url) as pool, http_client() as client:
        history = GatewayHistory(settings.gateway_base_url, client)
        hub = Hub()
        # Shared with the job runner below, not one semaphore each — two gates that
        # happen to share a number would still let a deep job starve an interactive
        # read the way a single gate cannot (design.md, "Zlecenia dzielą budżet ruchu
        # z resztą modułu").
        fill_limiter = asyncio.Semaphore(settings.backfill_concurrency)
        ingest = Ingest(
            pool,
            history,
            settings.gateway_stream_url,
            default_bars=settings.default_backfill_bars,
            backfill_concurrency=settings.backfill_concurrency,
            limiter=fill_limiter,
            sink=candle_sink(pool, hub),
        )
        job_runner = JobRunner(
            pool, history, limiter=fill_limiter, concurrency=settings.backfill_concurrency
        )

        app.state.settings = settings
        app.state.pool = pool
        app.state.hub = hub
        app.state.history = history
        app.state.instruments = GatewayInstruments(settings.gateway_base_url, client)
        app.state.ingest = ingest
        app.state.job_runner = job_runner

        # Before anything else touches the job tables: no runner survives a restart, so
        # any chunk left `pending` or `running` from before this start was orphaned, not
        # merely delayed (jobs/store.py, `interrupt_orphaned_chunks`).
        async with pool.acquire() as conn:
            interrupted = await interrupt_orphaned_chunks(conn)
        if interrupted:
            log.info("collection jobs: %d orphaned chunk(s) marked interrupted at startup", interrupted)

        await ingest.start()
        await job_runner.start()
        try:
            yield
        finally:
            await job_runner.stop()
            await ingest.stop()


app = FastAPI(
    title="TradingCenter · market-data",
    description=(
        "The candle archive. Reads a range with the parts it never collected marked, "
        "serves a subscription whose first message is a snapshot, and manages which pairs "
        "are collected. Candles are built from the **bid** side, matching capital-gateway. "
        "The WebSocket at /ws/candles is not described by this schema — see the module "
        "README."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


@app.exception_handler(TrackingRefused)
async def _tracking_refused(request: Request, exc: TrackingRefused) -> JSONResponse:
    # 409 rather than 400: nothing about the request was malformed, the archive is simply
    # not in a state where it can be honoured.
    status = 409 if isinstance(exc, LimitReached) else 422
    return JSONResponse(status_code=status, content={"detail": str(exc)})


@app.exception_handler(FutureRequest)
async def _future_request(request: Request, exc: FutureRequest) -> JSONResponse:
    # 422 and the reason in full: a start date after now is a request the module will
    # never be able to honour, and the caller's next move is to pick a different date —
    # which it can only do if told that is the problem (`market-data-jobs` spec, "Data w
    # przyszłości"). Without this it fell to the catch-all below and read as a 500, which
    # says "the archive broke" about a request that was simply wrong.
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(GatewayError)
async def _gateway_error(request: Request, exc: GatewayError) -> JSONResponse:
    # 502/504: the failure is upstream, and saying so keeps a consumer from retrying the
    # archive as though the archive were at fault.
    status = 504 if isinstance(exc, GatewayUnreachable) else 502
    return JSONResponse(status_code=status, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    # Nothing raw reaches a consumer. A database error names tables and columns, which is
    # more than a caller can use and more than a log should carry; the detail goes to the
    # log and the caller gets something it can act on.
    log.exception("unhandled error serving %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "the archive failed to answer this request; see its logs"},
    )


def pool(request: Request):
    return request.app.state.pool


def hub(websocket: WebSocket) -> Hub:
    # A WebSocket connection is not a Request: asking for one here leaves FastAPI with
    # nothing to pass, and the handshake fails before it is ever accepted.
    return websocket.app.state.hub


@app.get("/", tags=["meta"])
async def root() -> dict:
    return {"service": "market-data", "docs": "/docs"}


@app.get("/health", tags=["meta"])
async def health(request: Request) -> dict:
    """Whether the archive can answer at all, which means whether its database can."""
    async with request.app.state.pool.acquire() as conn:
        await conn.fetchval("SELECT 1")
    ingest: Ingest = request.app.state.ingest
    return {
        "database": "reachable",
        "collecting": len(ingest.running),
        "started_at": ingest.started_at.isoformat() if ingest.started_at else None,
    }


# --- candles ---


@app.get(
    "/candles/{symbol}",
    tags=["candles"],
    response_model=CandlesOut,
    responses={422: {"model": Problem}},
    summary="Candles for one pair over a time range",
    description=(
        "Answers with the series and, separately, the stretches of the requested range "
        "the archive never verified. Those are not the same as periods with no candle: a "
        "closed market has no candle either, and only one of the two is missing data.\n\n"
        + DERIVED_NOTE
    ),
)
async def candles(
    symbol: str,
    resolution: Resolution = Query(Resolution.MINUTE),
    from_: datetime | None = Query(None, alias="from", description="inclusive, UTC"),
    to: datetime | None = Query(None, description="exclusive, UTC"),
    db=Depends(pool),
) -> CandlesOut:
    start, end = _window(from_, to, resolution)

    async with db.acquire() as conn:
        # Collected beats computed, and the order matters more than it looks. A
        # resolution being *derivable* does not mean this pair was derived: an operator
        # may track a pair at HOUR, in which case ingest fetches and stores the
        # provider's own hourly candles and nothing ever builds a rollup for it, because
        # rollups are refreshed off the minute series that pair does not have. Reading
        # the rollup table unconditionally answered such a pair with an empty series
        # while coverage said the range was verified — which reads as "the market was
        # shut all day", the one confident wrong answer this module exists to prevent.
        series: list[Candle] = list(await read_candles(conn, symbol, resolution, start, end))
        derived = False
        if not series and resolution in DERIVABLE:
            series = list(await read_derived(conn, symbol, resolution, start, end))
            derived = True
        gaps = await uncovered_within(conn, symbol, resolution, start, end)

    return CandlesOut(
        symbol=symbol,
        resolution=resolution,
        price_side=PriceSide.BID,
        derived=derived,
        candles=[CandleOut.of(candle) for candle in series],
        uncovered=[Uncovered(from_=gap_start, to=gap_end) for gap_start, gap_end in gaps],
    )


@app.get(
    "/coverage/{symbol}",
    tags=["candles"],
    response_model=PairCoverageOut,
    summary="What the archive has verified for one pair",
)
async def coverage(
    symbol: str, resolution: Resolution = Query(Resolution.MINUTE), db=Depends(pool)
) -> PairCoverageOut:
    async with db.acquire() as conn:
        ranges = await read_coverage(conn, symbol, resolution)
        boundary = await earliest_reachable(conn, symbol, resolution)

    return PairCoverageOut(
        symbol=symbol,
        resolution=resolution,
        ranges=[
            CoverageOut(from_=r.range_start, to=r.range_end, history_ended=r.history_ended)
            for r in ranges
        ],
        earliest_reachable=boundary,
    )


# --- tracked pairs ---


@app.get(
    "/pairs",
    tags=["tracking"],
    response_model=list[TrackedPairOut],
    summary="Which pairs are collected, and whether collection is happening",
)
async def pairs(request: Request, db=Depends(pool)) -> list[TrackedPairOut]:
    moment = datetime.now(UTC)
    async with db.acquire() as conn:
        statuses = await read_status(conn, now=moment)

    decided = await _decide_late_pairs(request.app.state.instruments, statuses, moment)
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
            last_fill=_fill_out(ingest.last_fill(status.symbol, status.resolution)),
        )
        for status, collection in decided
    ]


# A market's status, remembered briefly. A session changes twice a day, so a minute of
# staleness costs nothing an operator can perceive — and without it a shut market is
# permanently "late", so every read of the list spends a gateway request per closed pair,
# forever. Measured over a quarter of an hour of a weekend: 74 requests about one
# instrument that had been shut since Friday.
_MARKET_STATUS_TTL = timedelta(minutes=1)
_market_status_cache: dict[str, tuple[datetime, bool | None]] = {}


async def _market_status(instruments: GatewayInstruments, symbol: str) -> tuple[str, bool | None]:
    """Whether this instrument's market is open, from cache when it is fresh enough.

    A gateway that will not answer is cached as `None` like any other answer: it would
    otherwise be re-asked on every read while it is down, which is when it can least
    afford the traffic.
    """
    now = datetime.now(UTC)
    remembered = _market_status_cache.get(symbol)
    if remembered is not None and now - remembered[0] < _MARKET_STATUS_TTL:
        return symbol, remembered[1]

    try:
        answer = await instruments.is_market_open(symbol)
    except GatewayError:
        answer = None

    _market_status_cache[symbol] = (now, answer)
    return symbol, answer


def _fill_out(outcome) -> FillOut | None:
    """The last fill for one pair, in the contract's shape.

    Kept out of the log and put here because the spec asks for exactly that: a fill can
    run for tens of minutes and fail on one pair while the rest carry on, and "what is
    being collected" is not answered without saying how that went. `None` means no fill
    has run since the module started — the record is in memory, so a restart empties it.
    """
    if outcome is None:
        return None
    return FillOut(
        finished_at=outcome.finished_at,
        requested=outcome.requested,
        written=outcome.written,
        requests=outcome.requests,
        failure=outcome.failure,
        summary=outcome.describe(),
    )


async def _decide_late_pairs(
    instruments: GatewayInstruments,
    statuses: list,
    moment: datetime,
) -> list[tuple]:
    """Turn `UNKNOWN` into `STALLED` or `MARKET_CLOSED` where the gateway can say which.

    **Only the late ones are asked about.** A pair whose newest candle is fresh reads
    `COLLECTING` whatever the market is doing, so a request about it would spend the
    gateway's shared allowance to learn nothing that changes an answer. On a healthy
    archive that leaves nothing to ask, and this costs one round trip per late *symbol* —
    not per pair, because the same instrument at two resolutions has one market.

    A gateway that will not answer leaves the state `UNKNOWN`, which is what it already
    was. The list is the archive's own and worth returning; not knowing why one pair is
    late is not a reason to fail the whole read.
    """
    late = sorted(
        {status.symbol for status in statuses if status.collection is CollectionState.UNKNOWN}
    )
    if not late:
        return [(status, status.collection) for status in statuses]

    open_now = dict(await asyncio.gather(*(_market_status(instruments, s) for s in late)))

    decided = []
    for status in statuses:
        collection = status.collection
        if collection is CollectionState.UNKNOWN:
            is_open = open_now.get(status.symbol)
            if is_open is not None:
                collection = collection_state(
                    status.resolution, status.latest_candle, moment, is_open
                )
        decided.append((status, collection))
    return decided


def _tracked_pair_out(pair: TrackedPair) -> TrackedPairOut:
    return TrackedPairOut(
        symbol=pair.symbol,
        resolution=pair.resolution,
        added_at=pair.added_at,
        collect_from=pair.collect_from,
        earliest_candle=None,
        latest_candle=None,
        collection="never_collected",
    )


@app.post(
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
                symbol=pair.symbol, resolution=pair.resolution, pair=_tracked_pair_out(pair)
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
            pair_plans, _ = await plan_chunks(
                conn, pair.symbol, pair.resolution, pair.collect_from, now
            )
            plans.extend(pair_plans)
        job = await create_job(conn, body.collect_from or now, plans)
    state.job_runner.notify()

    return TrackPairsResult(results=results, job_id=job.id)


@app.delete(
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


@app.get(
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


# --- collection jobs ---


@app.post(
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


@app.get(
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


@app.get(
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


@app.post(
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


# --- the subscription ---
#
# Not in the OpenAPI schema: OpenAPI has no vocabulary for WebSocket payloads. The message
# shapes are pydantic models in `hub.py` and are documented in the module README. There is
# a test that keeps this path out of the schema, so the README stays the only description
# rather than becoming the second one.


@app.websocket("/ws/candles")
async def candle_feed(websocket: WebSocket, the_hub: Hub = Depends(hub)) -> None:
    """A snapshot, then every change.

    The subscription is the query string, so there is no client protocol to get wrong.
    """
    symbol = (websocket.query_params.get("symbol") or "").strip().upper()
    raw_resolution = websocket.query_params.get("resolution") or Resolution.MINUTE.value

    if not symbol:
        await websocket.close(code=1008, reason="symbol is required")
        return
    try:
        resolution = Resolution(raw_resolution)
    except ValueError:
        await websocket.close(code=1008, reason=f"unknown resolution {raw_resolution!r}")
        return

    db = websocket.app.state.pool
    async with db.acquire() as conn:
        if not await is_tracked(conn, symbol, resolution):
            # Refused before the handshake. Accepting and then closing would look like a
            # feed that died rather than a pair nobody chose to collect — and subscribing
            # must not quietly start collecting it, because that is the decision the
            # ceiling exists to keep deliberate.
            await websocket.close(
                code=1008, reason=f"{symbol} {resolution.value} is not being collected"
            )
            return

    await websocket.accept()

    async def send(message) -> None:
        await websocket.send_json(message.model_dump(mode="json"))

    async def read_settled() -> list[Candle]:
        async with db.acquire() as conn:
            return list(await read_recent(conn, symbol, resolution, SNAPSHOT_CANDLES))

    await the_hub.subscribe(symbol, resolution, send, read_settled)
    try:
        # Nothing to read, but receiving is how a disconnect is noticed; without it the
        # handler returns and the socket closes.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await the_hub.unsubscribe(symbol, resolution, send)


def _window(
    from_: datetime | None, to: datetime | None, resolution: Resolution
) -> tuple[datetime, datetime]:
    """The requested range, with defaults and both ends carrying a zone.

    A naive bound is read as UTC rather than refused: it is the commonest way to write one
    by hand, and the archive stores instants, so the alternative is a 422 for something
    that has exactly one sensible reading.
    """
    end = to or datetime.now(UTC)
    start = from_ or end - timedelta(days=1)
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    if end < start:
        # A refusal, not a failure. The request is the thing that is wrong, and answering
        # 500 would send a caller looking for a fault in the archive.
        raise HTTPException(
            status_code=422,
            detail=f"`to` is before `from`: {start.isoformat()} to {end.isoformat()}",
        )
    return start, end
