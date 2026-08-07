"""The published surface: FastAPI over the archive, plus the subscription.

The one thing worth reading twice is `/ws/candles`. Its first message is a snapshot and
every message after it is a change, and the two are joined here rather than by whoever is
consuming them. That is the whole reason the seam stopped being the terminal's problem:
the snapshot is read while the room is held still and the subscriber attaches before it is
released, so no candle can fall between them and none can arrive twice.
"""

from __future__ import annotations

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
    PairCoverageOut,
    Problem,
    TrackedPairOut,
    TrackPairRequest,
    Uncovered,
)
from .coverage import earliest_reachable, read_coverage, uncovered_within
from .db import pool as make_pool
from .errors import GatewayError, GatewayUnreachable
from .gateway import GatewayHistory, GatewayInstruments, http_client
from .hub import Hub
from .ingest import Ingest
from .ingest.live import store_closed_candle
from .models import Candle, PriceSide, Resolution
from .rollups import DERIVABLE, read_derived
from .store import read_candles, read_recent
from .tracking import (
    LimitReached,
    TrackingRefused,
    add_pair,
    is_tracked,
    read_status,
    untrack,
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
        ingest = Ingest(
            pool,
            history,
            settings.gateway_stream_url,
            default_bars=settings.default_backfill_bars,
            backfill_concurrency=settings.backfill_concurrency,
            sink=candle_sink(pool, hub),
        )

        app.state.settings = settings
        app.state.pool = pool
        app.state.hub = hub
        app.state.history = history
        app.state.instruments = GatewayInstruments(settings.gateway_base_url, client)
        app.state.ingest = ingest

        await ingest.start()
        try:
            yield
        finally:
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


def hub(request: Request) -> Hub:
    return request.app.state.hub


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
    derived = resolution in DERIVABLE

    async with db.acquire() as conn:
        if derived:
            series: list[Candle] = list(await read_derived(conn, symbol, resolution, start, end))
        else:
            series = list(await read_candles(conn, symbol, resolution, start, end))
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
async def pairs(db=Depends(pool)) -> list[TrackedPairOut]:
    async with db.acquire() as conn:
        statuses = await read_status(conn)
    return [
        TrackedPairOut(
            symbol=status.symbol,
            resolution=status.resolution,
            added_at=status.added_at,
            latest_candle=status.latest_candle,
            collection=status.collection,
        )
        for status in statuses
    ]


@app.post(
    "/pairs",
    tags=["tracking"],
    response_model=TrackedPairOut,
    status_code=201,
    responses={409: {"model": Problem}, 422: {"model": Problem}, 504: {"model": Problem}},
    summary="Start collecting a pair",
    description=(
        "Validated against the gateway first, so a symbol the provider cannot serve is "
        "refused rather than left on the list collecting nothing. Refused with 409 when "
        "the configured ceiling is full — the ceiling is real, because the gateway holds "
        "one provider connection per pair."
    ),
)
async def track_pair(body: TrackPairRequest, request: Request) -> TrackedPairOut:
    state = request.app.state
    async with state.pool.acquire() as conn:
        pair = await add_pair(
            conn,
            state.instruments,
            body.symbol,
            body.resolution,
            state.settings.max_tracked_pairs,
        )
    # Collection starts now rather than at the next restart.
    await state.ingest.sync()

    return TrackedPairOut(
        symbol=pair.symbol,
        resolution=pair.resolution,
        added_at=pair.added_at,
        latest_candle=None,
        collection="never_collected",
    )


@app.delete(
    "/pairs/{symbol}",
    tags=["tracking"],
    status_code=204,
    responses={404: {"model": Problem}},
    summary="Stop collecting a pair",
    description="The candles already collected stay. An archive that deletes on a "
    "configuration change is not an archive.",
)
async def untrack_pair(
    symbol: str, request: Request, resolution: Resolution = Query(Resolution.MINUTE)
):
    async with request.app.state.pool.acquire() as conn:
        stopped = await untrack(conn, symbol, resolution)
    if stopped is None:
        return JSONResponse(
            status_code=404,
            content={"detail": f"{symbol} {resolution.value} is not being collected"},
        )
    await request.app.state.ingest.sync()
    return JSONResponse(status_code=204, content=None)


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
