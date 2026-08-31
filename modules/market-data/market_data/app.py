"""The published surface: FastAPI over the archive, plus the subscription. Only assembly lives
here; the routes are in `routers/`, split by the area they serve rather than by verb."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from datetime import timedelta

from tc_runtime import migrate, schema_version

from . import telemetry

# Must run before `from fastapi import FastAPI` below, not merely before `FastAPI(...)` is called:
# the auto-instrumentation patches the class attribute, and the import binds this module's name.
telemetry.configure()

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .caller_access import CallerAccess
from .config import Settings
from .db import MIGRATION_LOCK_KEY, advisory_lock
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
from .routers import candles, indicators, instruments, jobs, meta, pairs, stream
from .runtime import MIGRATIONS
from .tickets import TicketStore
from .tracking import LimitReached, TrackingRefused

log = logging.getLogger(__name__)


def candle_sink(pool, hub: Hub):
    """Where ingest sends every candle it sees. The storing happens inside the hub's hold: a write
    committing outside it lands between a subscriber's snapshot and its attachment, and arrives twice."""

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
        http_client(settings.gateway_api_key, settings.gateway_scope) as client,
    ):
        # The database is brought to this image's revision before anything is built on it and
        # before a candle is written. One connection throughout: the advisory lock is session scoped.
        async with pool.acquire() as conn:
            async with advisory_lock(
                conn, MIGRATION_LOCK_KEY, wait=settings.migration_lock_wait_seconds
            ):
                await migrate.run(MIGRATIONS)
            # Still checked, for a narrower pair of accidents: a migration that reported success
            # without arriving, and an image older than the schema it found.
            await schema_version.verify(conn, MIGRATIONS)

        history = GatewayHistory(settings.gateway_base_url, client)
        hub = Hub()
        # Shared with the job runner below, not one semaphore each: two gates sharing a number
        # would still let a deep job starve an interactive read the way a single gate cannot.
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
        # Lives as long as the process. A restart voids the tickets in flight, which costs at
        # most one failed handshake — the consumer asks for another and tries again.
        app.state.tickets = TicketStore(timedelta(seconds=settings.stream_ticket_ttl_seconds))
        app.state.history = history
        app.state.instruments = GatewayInstruments(settings.gateway_base_url, client)
        app.state.ingest = ingest
        app.state.job_runner = job_runner
        # Memory only: the gateway it asks is resolved per request from the line
        # above, so a caller swapping that out is answered by the new one.
        app.state.market_status = MarketStatus()
        # A recursive filter's loop holds the GIL, so this is a plain gate on how many requests
        # compute at once — a thread would not free the event loop the way it does for I/O.
        app.state.indicator_limiter = asyncio.Semaphore(settings.indicator_concurrency)

        candle_age = telemetry.CandleAgeGauge()
        candle_age_periods = telemetry.CandlePeriodsLateGauge()
        telemetry.register(candle_age, candle_age_periods)

        # Before anything else touches the job tables: no runner survives a restart, so a chunk
        # left `pending` or `running` from before this start was orphaned, not merely delayed.
        async with pool.acquire() as conn:
            interrupted = await interrupt_orphaned_chunks(conn)
        if interrupted:
            log.info("collection jobs: %d orphaned chunk(s) marked interrupted at startup", interrupted)

        await ingest.start()
        await job_runner.start()
        candle_age_task = asyncio.create_task(
            telemetry.refresh_loop(
                pool,
                app.state.instruments,
                app.state.market_status,
                candle_age,
                candle_age_periods,
            )
        )
        # The tool surface's own machinery, started here because a mounted application's
        # lifespan is not run by the one mounting it (`mcp_app.tool_surface_session`).
        from .mcp_app import tool_surface_session

        try:
            async with tool_surface_session(app):
                yield
        finally:
            candle_age_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await candle_age_task
            await job_runner.stop()
            await ingest.stop()

async def _tracking_refused(request: Request, exc: TrackingRefused) -> JSONResponse:
    # 409 rather than 400: nothing about the request was malformed, the archive is simply
    # not in a state where it can be honoured.
    status = 409 if isinstance(exc, LimitReached) else 422
    return JSONResponse(status_code=status, content={"detail": str(exc)})


async def _future_request(request: Request, exc: FutureRequest) -> JSONResponse:
    # 422 and the reason in full: a start date after now is a request the module can never honour,
    # and the caller's next move is a different date — which it can only pick if told that is it.
    return JSONResponse(status_code=422, content={"detail": str(exc)})


async def _gateway_error(request: Request, exc: GatewayError) -> JSONResponse:
    # 502/504: the failure is upstream, and saying so keeps a consumer from retrying the
    # archive as though the archive were at fault.
    status = 504 if isinstance(exc, GatewayUnreachable) else 502
    return JSONResponse(status_code=status, content={"detail": str(exc)})


async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    # Nothing raw reaches a consumer: a database error names tables and columns, which is more
    # than a caller can use and more than a log should carry.
    log.exception("unhandled error serving %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "the archive failed to answer this request; see its logs"},
    )


def create_app() -> FastAPI:
    """One assembled application, owning nothing that outlives it. A module-level object makes
    `app.state` a global one test hands to the next, which twenty of them did."""
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

    # No CORS middleware here: Easy Auth would answer the credential-free preflight with a 401
    # first, so App Service answers CORS in front of it, and two layers would double the header.

    # The subscription's message shapes, hung on the document FastAPI builds from the routes.
    # Mutating the cached dict means the served `/openapi.json` and the dumped one are one contract.
    routes_openapi = app.openapi

    def openapi_with_stream() -> dict:
        return require_response_fields(add_stream_messages(routes_openapi()))

    app.openapi = openapi_with_stream  # type: ignore[method-assign]

    app.add_exception_handler(TrackingRefused, _tracking_refused)  # type: ignore[arg-type]
    app.add_exception_handler(FutureRequest, _future_request)  # type: ignore[arg-type]
    app.add_exception_handler(GatewayError, _gateway_error)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled)  # type: ignore[arg-type]

    # Order matches the single module these came out of, so the published document lists its paths
    # exactly where it always did. `instruments` and `indicators` are newer and go last.
    for area in (meta, candles, pairs, jobs, stream, instruments, indicators):
        app.include_router(area.router)

    # A mounted ASGI application rather than a router: what the MCP library builds is a Starlette
    # app. Imported inside the factory so it cannot climb above `telemetry.configure()`.
    from .mcp_app import ToolSurfaceAddress, build_mcp_app

    mcp_server, mcp_asgi = build_mcp_app(app)
    # Kept on the application so the lifespan can start its session manager: the mounted app's
    # own lifespan never runs, and without that task group every tool call fails.
    app.state.mcp_server = mcp_server
    app.mount("/mcp", mcp_asgi)

    # One layer rather than a dependency per router: `/mcp` is a mounted app, so `dependencies=`
    # could not reach it. Added first, so it ends up inside the caller-access layer.
    app.add_middleware(ToolSurfaceAddress)
    app.add_middleware(CallerAccess, state=app.state)

    return app


# The ASGI entrypoint every deployment names — `uvicorn market_data.app:app` in the
# Dockerfile, in `scripts/dev.py` and in the README.
app = create_app()
