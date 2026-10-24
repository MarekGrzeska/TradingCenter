"""The published surface: FastAPI over strategies and their runs. Only assembly lives here.

A package of the workbench process: the host mounts `create_app()` under `/strategies` — when its database is configured,
and not otherwise — and enters `serving` from its own lifespan, because a mounted application's lifespan is never run.
"""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack, asynccontextmanager

import httpx
from fastapi import FastAPI
from tc_runtime import migrate, schema_version
from tc_runtime.db import advisory_lock
from tc_runtime.db import pool as make_pool

from .archive import Archive
from .caller_access import RECORD, CallerAccess
from .config import Settings
from .queue import RunQueue
from .routers import language, meta, runs, strategies
from .runtime import MIGRATION_LOCK_KEY, MIGRATIONS

log = logging.getLogger(__name__)


@asynccontextmanager
async def serving(app: FastAPI, settings: Settings, *, market: httpx.AsyncClient | None = None):
    """Everything this package needs running, on `app.state`, for as long as the block is open. `market` is the host's
    client over the candle archive's REST contract; without it documents can be written but not checked against what
    the archive holds, nor run."""
    app.state.settings = settings
    app.state.archive = Archive(market)

    async with AsyncExitStack() as stack:
        try:
            pool = await stack.enter_async_context(
                make_pool(
                    settings.database_url,
                    user=settings.database_user,
                    client_id=settings.azure_client_id,
                    client_secret=settings.azure_client_secret,
                    tenant_id=settings.azure_tenant_id,
                    max_size=settings.database_pool_size,
                )
            )
            # One connection held for the whole of it: the advisory lock is session scoped, so handing the connection
            # back to the pool in between would release it early.
            async with pool.acquire() as conn:
                async with advisory_lock(conn, MIGRATION_LOCK_KEY, wait=settings.migration_lock_wait_seconds):
                    await migrate.run(MIGRATIONS)
                await schema_version.verify(conn, MIGRATIONS)
        except Exception as err:
            # Named, because the first thing in the log is otherwise a socket error that says nothing of whose database.
            raise RuntimeError(
                f"the strategies database could not be opened or migrated: {type(err).__name__}: {err}"
            ) from err

        app.state.pool = pool
        # After the migration: the queue's first act is marking what a previous process left running.
        app.state.queue = RunQueue(pool, app.state.archive, settings)
        await app.state.queue.start()
        log.info("strategies is serving")
        try:
            yield
        finally:
            await app.state.queue.stop()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Standalone: the settings read from this process's environment, then `serving`."""
    settings = Settings()  # type: ignore[call-arg]
    async with serving(app, settings):
        yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="strategies",
        version="0.1.0",
        summary="Strategies as documents, and backtests of them over the candle archive — research, never an order.",
        lifespan=lifespan,
    )
    app.include_router(meta.router)
    app.include_router(language.router)
    app.include_router(strategies.router)
    app.include_router(runs.router)

    # In front of the whole application: nothing decides who may call after routing has begun.
    app.add_middleware(CallerAccess, state=app.state, record=RECORD)
    return app


app = create_app()
