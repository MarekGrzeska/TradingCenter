"""The published surface: FastAPI over the post archive. Only assembly lives here, and the order inside
the lifespan is what to read twice: the database is migrated before anything is written."""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from tc_runtime import migrate, schema_version
from tc_runtime.db import advisory_lock
from tc_runtime.db import pool as make_pool

from .config import Settings
from .ingest import Ingest
from .providers.truth_social import TruthSocialFeed
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

    async with (
        make_pool(
            settings.database_url,
            user=settings.database_user,
            client_id=settings.azure_client_id,
            client_secret=settings.azure_client_secret,
            tenant_id=settings.azure_tenant_id,
        ) as pool,
        httpx.AsyncClient(
            timeout=httpx.Timeout(settings.provider_timeout_seconds, connect=10.0),
            headers={
                "User-Agent": settings.provider_user_agent,
                "Accept": "application/rss+xml, application/xml;q=0.9",
            },
            follow_redirects=True,
        ) as http,
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

        # After the migration and not before it: a pass started earlier would write into a schema
        # it does not know, and a bad write is not undone by a later error response.
        ingest = Ingest(
            pool,
            [TruthSocialFeed(http, feed_url=settings.truth_social_feed_url)],
            interval_seconds=settings.collect_interval_seconds,
            window_hours=settings.collect_window_hours,
        )
        app.state.ingest = ingest
        await ingest.start()

        log.info("social-data is serving")
        try:
            yield
        finally:
            await ingest.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title="social-data",
        version="0.1.0",
        summary="The post archive — what was said, when, and what a model made of it.",
        lifespan=lifespan,
    )
    app.include_router(meta.router)
    return app


app = create_app()
