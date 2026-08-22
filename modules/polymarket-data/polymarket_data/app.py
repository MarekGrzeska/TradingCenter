"""The published surface: FastAPI over the prediction-market archive.

Only assembly lives here — the lifespan and the routers. The one thing worth reading twice
is the order inside the lifespan: the database is brought to this image's revision before
anything is built on top of it, before a request is served and before a single price
sample is written. Sampling starts at the bottom of this file for exactly that reason.
"""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from tc_runtime import migrate, schema_version
from tc_runtime.db import advisory_lock
from tc_runtime.db import pool as make_pool

from . import provider
from .config import Settings
from .ingest import Ingest
from .routers import meta
from .runtime import MIGRATION_LOCK_KEY, MIGRATIONS

log = logging.getLogger(__name__)


def configure_logging() -> None:
    """Give the root logger a level and somewhere to write, because nothing else does.

    Uvicorn configures its own three loggers and leaves the root alone, so without this a
    deployed container prints the access log and not one line this module wrote — the
    root logger's default level is WARNING and it has no handler regardless. `market-data`
    learned this the expensive way: a collection job that never started looked exactly
    like one running quietly.

    `basicConfig` is a no-op if the root logger already has a handler, which is the right
    behaviour — a caller who configured logging themselves keeps their configuration.
    """
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

    async with (
        make_pool(
            settings.database_url,
            user=settings.database_user,
            client_id=settings.azure_client_id,
            client_secret=settings.azure_client_secret,
            tenant_id=settings.azure_tenant_id,
        ) as pool,
        provider.client(
            gamma_base_url=settings.gamma_base_url,
            clob_base_url=settings.clob_base_url,
            user_agent=settings.provider_user_agent,
            concurrency=settings.provider_concurrency,
        ) as polymarket,
    ):
        # One connection held for the whole of it: the advisory lock is session scoped, so
        # it has to be released on the connection that took it, and handing that connection
        # back to the pool in between would release it early.
        async with pool.acquire() as conn:
            async with advisory_lock(
                conn, MIGRATION_LOCK_KEY, wait=settings.migration_lock_wait_seconds
            ):
                await migrate.run(MIGRATIONS)
            # Still checked after migrating, for the pair a migration cannot fix: an
            # upgrade that reported success without arriving, and an image older than the
            # schema it found.
            await schema_version.verify(conn, MIGRATIONS)

        app.state.pool = pool
        app.state.provider = polymarket

        # After the migration and not before it: sampling started earlier would write to a
        # schema it does not know, and a bad write is not undone by a later error response.
        ingest = Ingest(
            pool,
            polymarket,
            interval_seconds=settings.sample_interval_seconds,
            window_days=settings.history_window_days,
            default_backfill_days=settings.default_backfill_days,
        )
        app.state.ingest = ingest
        await ingest.start()
        log.info("polymarket-data is serving")
        try:
            yield
        finally:
            await ingest.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title="polymarket-data",
        version="0.1.0",
        summary="The prediction-market archive — one door to Polymarket, one database.",
        lifespan=lifespan,
    )
    app.include_router(meta.router)
    return app


app = create_app()
