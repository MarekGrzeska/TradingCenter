"""The published surface: FastAPI over the YouTube archive. Only assembly lives here, and the order inside `serving` is
what to read twice: the database is migrated before anything is written.

A package of the workbench process: the host mounts `create_app()` under `/youtube` — when its database is configured,
and not otherwise — and enters `serving` from its own lifespan, because a mounted application's lifespan is never run.
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

from . import alerts, mcp_app
from .caller_access import RECORD, CallerAccess
from .config import Settings
from .ingest import Ingest
from .providers import build as providers_build
from .routers import candidates as candidates_routes
from .routers import meta, videos, watch
from .routers import prompts as prompts_routes
from .runtime import MIGRATION_LOCK_KEY, MIGRATIONS

log = logging.getLogger(__name__)


@asynccontextmanager
async def serving(app: FastAPI, settings: Settings, alerts_client: httpx.AsyncClient | None = None):
    """Everything this package needs running, on `app.state`, for as long as the block is open. `alerts_client` is the host's
    client over the alerts package; without it nobody is told, whatever the rules say."""
    app.state.settings = settings

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

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.provider_timeout_seconds, connect=10.0),
            headers={"User-Agent": settings.provider_user_agent},
            follow_redirects=True,
        ) as http:
            providers = providers_build.build(settings, http)
            app.state.providers = providers

            # After the migration and not before it: a pass started earlier would write into a schema it does not know.
            # One heartbeat for the one loop, on the state so `/health` can answer with it and the metric can read it.
            heartbeats = Heartbeats(LoopHeartbeat("ingest", expected_seconds=settings.poll_interval_seconds))
            app.state.heartbeats = heartbeats
            liveness.register_metrics("youtube_data", heartbeats)

            # `None` without an alerts package, and this one runs anyway: reading without telling anybody is a supported
            # state, which `/state` names rather than leaving the screen to guess at.
            announcer = alerts.build(pool, settings, alerts_client)
            app.state.alerts = announcer
            if announcer is not None:
                await announcer.announce_types()

            ingest = Ingest(
                pool,
                providers,
                settings,
                announce=None if announcer is None else announcer.run,
                heartbeat=heartbeats["ingest"],
            )
            app.state.ingest = ingest
            await ingest.start()

            # The tool surface's session manager: a mounted application's lifespan is never run, so the task group has
            # to be started here or every tool call fails.
            async with mcp_app.tool_surface_session(app):
                log.info("youtube-data is serving")
                try:
                    yield
                finally:
                    await ingest.stop()
                    await providers.aclose()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Standalone: the settings read from this process's environment, then `serving`."""
    settings = Settings()  # type: ignore[call-arg]
    async with serving(app, settings):
        yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="youtube-data",
        version="0.1.0",
        summary="The YouTube archive — what was said in the films the operator follows, and what a model made of it.",
        lifespan=lifespan,
    )
    app.include_router(meta.router)
    app.include_router(videos.router)
    app.include_router(watch.router)
    app.include_router(prompts_routes.router)
    app.include_router(candidates_routes.router)

    server, tool_app = mcp_app.build_mcp_app(app)
    app.state.mcp_server = server
    app.mount(mcp_app.MOUNT_PATH, tool_app)

    # In front of the whole application, and in this order: the address fix runs before routing, and the caller record
    # before that, so nothing decides who may call after routing has begun.
    app.add_middleware(mcp_app.ToolSurfaceAddress)
    app.add_middleware(CallerAccess, state=app.state, record=RECORD)
    return app


app = create_app()
