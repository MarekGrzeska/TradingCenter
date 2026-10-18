"""The published surface: FastAPI over the alert rules. Only assembly lives here, and the order inside `serving` is what
to read twice: the database is migrated before anything is written.

A package of the workbench process: the host mounts `create_app()` under `/alerts` — when its database is configured,
and not otherwise — and enters `serving` from its own lifespan, because a mounted application's lifespan is never run.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from tc_runtime import migrate, schema_version
from tc_runtime.db import advisory_lock
from tc_runtime.db import pool as make_pool

from .caller_access import RECORD, CallerAccess
from .catalog import ToolSource
from .config import Settings
from .gateway import Gateway
from .routers import catalog, events, meta, rules
from .runtime import MIGRATION_LOCK_KEY, MIGRATIONS

log = logging.getLogger(__name__)


@asynccontextmanager
async def serving(
    app: FastAPI,
    settings: Settings,
    *,
    tools: ToolSource | None = None,
    telegram: httpx.AsyncClient | None = None,
):
    """Everything this package needs running, on `app.state`, for as long as the block is open. `tools` is the process's
    tool surface and `telegram` the host's client over the door to Telegram; without either, rules can still be written —
    against nothing the package can check, which the catalogue says."""
    app.state.settings = settings
    app.state.tools = tools
    app.state.gateway = None if telegram is None else Gateway(telegram)

    async with make_pool(
        settings.database_url,
        user=settings.database_user,
        client_id=settings.azure_client_id,
        client_secret=settings.azure_client_secret,
        tenant_id=settings.azure_tenant_id,
        max_size=settings.database_pool_size,
    ) as pool:
        # One connection held for the whole of it: the advisory lock is session scoped, so handing the connection back
        # to the pool in between would release it early.
        async with pool.acquire() as conn:
            async with advisory_lock(
                conn, MIGRATION_LOCK_KEY, wait=settings.migration_lock_wait_seconds
            ):
                await migrate.run(MIGRATIONS)
            # Still checked after migrating, for the pair a migration cannot fix: an upgrade that reported success
            # without arriving, and an image older than the schema it found.
            await schema_version.verify(conn, MIGRATIONS)

        app.state.pool = pool
        log.info("alerts is serving")
        yield


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Standalone: the settings read from this process's environment, then `serving`."""
    settings = Settings()  # type: ignore[call-arg]
    async with serving(app, settings):
        yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="alerts",
        version="0.1.0",
        summary="Who is told what, and when — the rules the operator sets, and the events and values they watch.",
        lifespan=lifespan,
    )
    app.include_router(meta.router)
    app.include_router(catalog.router)
    app.include_router(rules.router)
    app.include_router(events.router)

    # In front of the whole application: nothing decides who may call after routing has begun.
    app.add_middleware(CallerAccess, state=app.state, record=RECORD)
    return app


app = create_app()
