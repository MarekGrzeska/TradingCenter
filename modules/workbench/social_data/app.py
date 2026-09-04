"""The published surface: FastAPI over the post archive. Only assembly lives here, and the order inside
`serving` is what to read twice: the database is migrated before anything is written.

A package of the workbench process since `one-process-per-security-boundary`: the host mounts `create_app()`
under `/social` and enters `serving` from its own lifespan, because a mounted application's lifespan is never
run. `app` and `lifespan` below are what `python -m social_data.openapi` and the tests build.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from tc_runtime import liveness, migrate, schema_version
from tc_runtime.db import advisory_lock
from tc_runtime.db import pool as make_pool
from tc_runtime.liveness import Heartbeats, LoopHeartbeat

from . import alerts, enrichment, mcp_app
from .caller_access import RECORD, CallerAccess
from .config import Settings
from .ingest import Ingest
from .providers.truth_social import TruthSocialFeed
from .routers import meta, posts
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

        # `None` without a key, and the module runs anyway: collecting without reading is a
        # supported state, which `/state` names rather than leaving the screen to guess at.
        enricher = enrichment.build(pool, settings)
        app.state.enrichment = enricher

        # `None` without a gateway, and the module runs anyway: collecting without telling anybody
        # is a supported state, which `/state` names rather than leaving the screen to guess at.
        announcer = alerts.build(pool, settings)
        app.state.alerts = announcer

        # After the migration and not before it: a pass started earlier would write into a schema
        # it does not know, and a bad write is not undone by a later error response.
        # One heartbeat per loop, on the state so `/health` can answer with it and so the metric's
        # callback can read it without awaiting. "collect" is what the alert's `loop` dimension says.
        heartbeats = Heartbeats(LoopHeartbeat("collect", expected_seconds=settings.collect_interval_seconds))
        app.state.heartbeats = heartbeats
        liveness.register_metrics("social_data", heartbeats)

        ingest = Ingest(
            pool,
            [TruthSocialFeed(http, feed_url=settings.truth_social_feed_url)],
            interval_seconds=settings.collect_interval_seconds,
            window_hours=settings.collect_window_hours,
            enrich=None if enricher is None else enricher.run,
            announce=None if announcer is None else announcer.run,
            heartbeat=heartbeats["collect"],
        )
        app.state.ingest = ingest
        await ingest.start()

        # The tool surface's session manager: a mounted application's lifespan is never run, so the
        # task group has to be started here or every tool call fails.
        async with mcp_app.tool_surface_session(app):
            log.info("social-data is serving")
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
        title="social-data",
        version="0.1.0",
        summary="The post archive — what was said, when, and what a model made of it.",
        lifespan=lifespan,
    )
    app.include_router(meta.router)
    app.include_router(posts.router)

    server, tool_app = mcp_app.build_mcp_app(app)
    app.state.mcp_server = server
    app.mount(mcp_app.MOUNT_PATH, tool_app)

    # In front of the whole application, and in this order: the address fix runs before routing, and
    # the caller record before that, so nothing decides who may call after routing has begun.
    app.add_middleware(mcp_app.ToolSurfaceAddress)
    app.add_middleware(CallerAccess, state=app.state, record=RECORD)
    return app


app = create_app()
