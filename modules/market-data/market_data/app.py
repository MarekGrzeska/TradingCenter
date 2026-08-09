"""The published surface: FastAPI over the archive, plus the subscription.

Only assembly lives here — the lifespan, the error handling every route shares, and the
routers themselves. The routes are in `routers/`, split by the area they serve rather than
by verb, because that is how the specs are organised and how changes actually arrive: a
change to jobs touches four routes that are all in one file and none of the others.

The one thing worth reading twice is `/ws/candles`, in `routers/stream.py`. Its first
message is a snapshot and every message after it is a change, and the two are joined there
rather than by whoever is consuming them. That is the whole reason the seam stopped being
the terminal's problem: the snapshot is read while the room is held still and the
subscriber attaches before it is released, so no candle can fall between them and none can
arrive twice.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import Settings
from .db import pool as make_pool
from .errors import GatewayError, GatewayUnreachable
from .gateway import GatewayHistory, GatewayInstruments, http_client
from .hub import Hub
from .ingest import Ingest
from .ingest.live import store_closed_candle
from .jobs import FutureRequest, JobRunner, interrupt_orphaned_chunks
from .market_status import MarketStatus
from .models import Candle
from .openapi import add_stream_messages, require_response_fields
from .routers import candles, instruments, jobs, meta, pairs, stream
from .tracking import LimitReached, TrackingRefused

log = logging.getLogger(__name__)


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

    async with (
        make_pool(
            settings.database_url,
            user=settings.database_user,
            client_id=settings.azure_client_id,
            client_secret=settings.azure_client_secret,
            tenant_id=settings.azure_tenant_id,
        ) as pool,
        http_client(settings.gateway_api_key) as client,
    ):
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
            gateway_api_key=settings.gateway_api_key,
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
        # Memory only: the gateway it asks is resolved per request from the line
        # above, so a caller swapping that out is answered by the new one.
        app.state.market_status = MarketStatus()

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
        "The WebSocket at /ws/candles has no path here — OpenAPI has no place for one — "
        "but the messages it sends are published as the `Snapshot` and `CandleChange` "
        "schemas, so a consumer can be generated against them."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# The subscription's message shapes, hung on the document FastAPI builds from the routes.
# Wrapping rather than replacing keeps FastAPI's own construction untouched, and mutating
# the dict it caches means the served `/openapi.json` and the dumped one are the same
# bytes — a generator reading one and a human reading the other must never see two
# different contracts (`openapi.py`).
_routes_openapi = app.openapi


def _openapi_with_stream() -> dict:
    return require_response_fields(add_stream_messages(_routes_openapi()))


app.openapi = _openapi_with_stream  # type: ignore[method-assign]


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


# Order matches the single module these came out of, so the published document lists its
# paths exactly where it always did. `instruments` is new — see its module docstring —
# and goes last, after everything this module owned before it.
for area in (meta, candles, pairs, jobs, stream, instruments):
    app.include_router(area.router)
