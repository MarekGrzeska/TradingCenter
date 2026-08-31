"""The published surface: FastAPI over the door to Telegram. Only assembly lives here, and the order
inside the lifespan is what to read twice: the database is migrated before anything is served."""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from tc_runtime import migrate, schema_version
from tc_runtime.db import advisory_lock
from tc_runtime.db import pool as make_pool

from .config import Settings
from .routers import meta
from .runtime import MIGRATION_LOCK_KEY, MIGRATIONS

log = logging.getLogger(__name__)


def configure_logging() -> None:
    """Give the root logger a level and somewhere to write, because nothing else does. Uvicorn configures
    only its own, so without this a deployed container prints the access log and nothing this module wrote."""
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = Settings()  # type: ignore[call-arg]
    app.state.settings = settings

    async with make_pool(
        settings.database_url,
        user=settings.database_user,
        client_id=settings.azure_client_id,
        client_secret=settings.azure_client_secret,
        tenant_id=settings.azure_tenant_id,
        max_size=settings.database_pool_size,
    ) as pool:
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
        log.info(
            "telegram-gateway is serving; creating bots is %s",
            "available" if settings.can_create_bots else "unavailable (no account session)",
        )
        yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="telegram-gateway",
        version="0.1.0",
        summary="The one door to Telegram — one notification, sent now, remembered by nobody.",
        lifespan=lifespan,
    )
    app.include_router(meta.router)
    return app


app = create_app()
