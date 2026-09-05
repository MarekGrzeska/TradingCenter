"""The published surface: FastAPI over the platform, plus the evaluation loop. `serving` is all-or-nothing, so a
process that answers proves it migrated — but it never reaches the archive, or it could not start while one restarts.

A package of the workbench process since `one-process-per-security-boundary`: the host mounts `create_app()` under
`/strategy` and enters `serving` from its own lifespan, because a mounted application's lifespan is never run. `app`
and `lifespan` below are what `python -m strategy.openapi` and the tests build.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from tc_runtime import liveness, migrate, schema_version
from tc_runtime.db import advisory_lock
from tc_runtime.db import pool as make_pool
from tc_runtime.liveness import Heartbeats, LoopHeartbeat

from . import alerts
from .archive import Archive, http_client
from .caller_access import RECORD, CallerAccess
from .config import Settings
from .errors import (
    ArchiveRefused,
    ArchiveUnreachable,
    StrategyError,
    UnknownDefinition,
    UnknownRevision,
    UnknownStrategy,
)
from .routers import backtests, decisions, definitions, meta, strategies
from .runner import EvaluationLoop
from .runtime import MIGRATION_LOCK_KEY, MIGRATIONS

log = logging.getLogger(__name__)


@asynccontextmanager
async def serving(app: FastAPI, settings: Settings):
    """Everything this package needs running, on `app.state`, for as long as the block is open."""
    # Constructed, not connected: reaching the archive at startup would make this process's health
    # depend on another module's, and there is nothing useful to do with the answer then.
    async with (
        make_pool(
            settings.database_url,
            user=settings.database_user,
            client_id=settings.azure_client_id,
            client_secret=settings.azure_client_secret,
            tenant_id=settings.azure_tenant_id,
            max_size=settings.database_pool_size,
        ) as pool,
        http_client(settings.market_data_scope) as client,
    ):
        # One connection held for the whole of it: the advisory lock is session scoped, so handing
        # the connection back to the pool in between would release it early.
        async with pool.acquire() as conn:
            async with advisory_lock(
                conn, MIGRATION_LOCK_KEY, wait=settings.migration_lock_wait_seconds
            ):
                log.info("bringing the database up to this image's revision")
                await migrate.run(MIGRATIONS)
            # Still checked, for a narrower pair of accidents: a migration that reported success
            # without arriving, and an image older than the schema it found.
            await schema_version.verify(conn, MIGRATIONS)

        app.state.settings = settings
        app.state.pool = pool
        app.state.archive = Archive(settings.market_data_url, client)

        # Started last, once everything a pass could need is on the state. A platform with no active
        # watches starts and serves the same way — zero is supported, not degraded.
        # `None` without a gateway, and the platform runs the same either way: deciding is its job,
        # and saying so is something it does when there is somewhere to say it.
        app.state.alerts = alerts.build(settings)

        # One heartbeat per loop, on the state so `/health` can answer with it and so the metric's
        # callback can read it without awaiting. "evaluate" is what the alert's `loop` dimension says.
        heartbeats = Heartbeats(LoopHeartbeat("evaluate", expected_seconds=settings.evaluation_interval_seconds))
        app.state.heartbeats = heartbeats
        liveness.register_metrics("strategy", heartbeats)

        loop = EvaluationLoop(
            pool,
            app.state.archive,
            interval_seconds=settings.evaluation_interval_seconds,
            alerts=app.state.alerts,
            heartbeat=heartbeats["evaluate"],
        )
        app.state.loop = loop
        loop.start()

        # The tool surface's own machinery, started here because a mounted application's
        # lifespan is not run by the one mounting it (`mcp_app.tool_surface_session`).
        from .mcp_app import tool_surface_session

        try:
            async with tool_surface_session(app):
                yield
        finally:
            await loop.aclose()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Standalone: the settings read from this process's environment, then `serving`."""
    settings = Settings()  # type: ignore[call-arg]
    async with serving(app, settings):
        yield


async def _refused(request: Request, exc: StrategyError) -> JSONResponse:
    # 404 for a strategy, definition or revision that is not there, 502/504 for the archive, 422 for
    # the rest. The archive's two are told apart because a consumer's next move differs.
    if isinstance(exc, UnknownStrategy | UnknownDefinition | UnknownRevision):
        status = 404
    elif isinstance(exc, ArchiveUnreachable):
        status = 504
    elif isinstance(exc, ArchiveRefused):
        status = 502
    else:
        status = 422
    return JSONResponse(status_code=status, content={"detail": str(exc)})


async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    # Nothing raw reaches a consumer. A database error names tables and columns, which is
    # more than a caller can use and more than a log should carry.
    log.exception("unhandled error serving %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "the platform failed to answer this request; see its logs"},
    )


def create_app() -> FastAPI:
    """One assembled application, owning nothing that outlives it. A module-level object would make
    `app.state` a global one test hands to the next."""
    app = FastAPI(
        title="TradingCenter · strategy",
        description=(
            "The strategy platform. A strategy is an entry in a catalogue — the facts it "
            "needs, the parameters it may be tuned with, and one pure function from those "
            "to a decision. This module evaluates on closed candles, records every "
            "decision with the reason and the facts it stood on, and publishes what it "
            "found. It never places an order: a setup here is a reading, and execution "
            "belongs to the teams and their limits."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_exception_handler(StrategyError, _refused)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled)  # type: ignore[arg-type]

    for area in (meta, strategies, definitions, decisions, backtests):
        app.include_router(area.router)

    # A mounted ASGI application rather than a router: what the MCP library builds is a Starlette app.
    # Handed the application rather than its state, because the state does not exist yet.
    from .mcp_app import ToolSurfaceAddress, build_mcp_app

    mcp_server, mcp_asgi = build_mcp_app(app)
    app.state.mcp_server = mcp_server
    app.mount("/mcp", mcp_asgi)

    # One layer rather than a dependency per router: `/mcp` is a mounted app, so `dependencies=` could
    # not reach it. Added first, so it ends up inside the caller-access layer.
    app.add_middleware(ToolSurfaceAddress)
    app.add_middleware(CallerAccess, state=app.state, record=RECORD)

    return app


app = create_app()
