"""The published surface: FastAPI over the prediction-market archive. Only assembly lives here, and the
order inside `serving` is what to read twice: the database is migrated before anything is written.

A package of the workbench process since `one-process-per-security-boundary`: the host mounts `create_app()`
under `/polymarket` and enters `serving` from its own lifespan, because a mounted application's lifespan is
never run. `app` and `lifespan` below are what `python -m polymarket_data.openapi` and the tests build.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from tc_runtime import liveness, migrate, schema_version
from tc_runtime.db import advisory_lock
from tc_runtime.db import pool as make_pool
from tc_runtime.liveness import Heartbeats, LoopHeartbeat

from . import mcp_app, provider
from .caller_access import RECORD, CallerAccess
from .config import Settings
from .ingest import Ingest
from .routers import groups, meta, observations, prices
from .runtime import MIGRATION_LOCK_KEY, MIGRATIONS

log = logging.getLogger(__name__)


@asynccontextmanager
async def serving(app: FastAPI, settings: Settings):
    """Everything this package needs running, on `app.state`, for as long as the block is open."""
    app.state.settings = settings

    async with (
        make_pool(
            settings.database_url,
            user=settings.database_user,
            client_id=settings.azure_client_id,
            client_secret=settings.azure_client_secret,
            tenant_id=settings.azure_tenant_id,
            max_size=settings.database_pool_size,
        ) as pool,
        provider.client(
            gamma_base_url=settings.gamma_base_url,
            clob_base_url=settings.clob_base_url,
            user_agent=settings.provider_user_agent,
            concurrency=settings.provider_concurrency,
        ) as polymarket,
    ):
        # One connection held for the whole of it: the advisory lock is session scoped, so handing
        # the connection back to the pool in between would release it early.
        async with pool.acquire() as conn:
            async with advisory_lock(
                conn, MIGRATION_LOCK_KEY, wait=settings.migration_lock_wait_seconds
            ):
                await migrate.run(MIGRATIONS)
            # Still checked after migrating, for the pair a migration cannot fix: an upgrade that
            # reported success without arriving, and an image older than the schema it found.
            await schema_version.verify(conn, MIGRATIONS)

        app.state.pool = pool
        app.state.provider = polymarket

        # After the migration and not before it: sampling started earlier would write to a
        # schema it does not know, and a bad write is not undone by a later error response.
        # One heartbeat per loop, on the state so `/health` can answer with it and so the metric's
        # callback can read it without awaiting. "sample" is what the alert's `loop` dimension says.
        heartbeats = Heartbeats(LoopHeartbeat("sample", expected_seconds=settings.sample_interval_seconds))
        app.state.heartbeats = heartbeats
        liveness.register_metrics("polymarket_data", heartbeats)

        ingest = Ingest(
            pool,
            polymarket,
            interval_seconds=settings.sample_interval_seconds,
            window_days=settings.history_window_days,
            default_backfill_days=settings.default_backfill_days,
            db_concurrency=settings.sampler_db_concurrency,
            heartbeat=heartbeats["sample"],
        )
        app.state.ingest = ingest
        await ingest.start()

        # The tool surface's session manager: a mounted application's lifespan is never run, so the
        # task group has to be started here or every tool call fails.
        async with mcp_app.tool_surface_session(app):
            log.info("polymarket-data is serving")
            try:
                yield
            finally:
                await ingest.stop()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Standalone: the settings read from this process's environment, then `serving`."""
    settings = Settings()  # type: ignore[call-arg]
    async with serving(app, settings):
        yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="polymarket-data",
        version="0.1.0",
        summary="The prediction-market archive — one door to Polymarket, one database.",
        lifespan=lifespan,
    )
    app.include_router(meta.router)
    app.include_router(observations.router)
    app.include_router(groups.router)
    app.include_router(prices.router)

    server, tool_app = mcp_app.build_mcp_app(app)
    app.state.mcp_server = server
    app.mount(mcp_app.MOUNT_PATH, tool_app)

    # In front of the whole application, and in this order: the address fix runs before routing, and
    # the caller record before that, so nothing decides who may call after routing has begun.
    app.add_middleware(mcp_app.ToolSurfaceAddress)
    app.add_middleware(CallerAccess, state=app.state, record=RECORD)
    return app


app = create_app()
