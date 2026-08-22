"""The published surface: FastAPI over the platform, plus the evaluation loop.

Assembly only — the lifespan, the error handling every route shares, and the routers.

**The lifespan is all-or-nothing on purpose.** The database is brought to this image's
revision before a single request is served, under an advisory lock, and a process that
answers is itself the proof that it got there — the deploy probe reaches the process
rather than the control plane, because App Service's control plane reported `Running`
over a crash-looping container on 16 August 2026.

What the lifespan does *not* do is reach the archive. A platform whose start depends on
another module's health is a platform that cannot come up while its upstream is
restarting; the loop finds out per evaluation instead, and says so in the decision it
records.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

# Root logger configuration, before anything else imports and starts logging. Nothing else
# sets a level or a destination — without this the process writes into the void, and a
# silent process looks exactly like an idle one.
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(levelname)-5.5s [%(name)s] %(message)s",
)

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from tc_runtime import migrate, schema_version
from tc_runtime.db import advisory_lock
from tc_runtime.db import pool as make_pool

from .archive import Archive, http_client
from .caller_access import CallerAccess
from .config import Settings
from .errors import ArchiveRefused, ArchiveUnreachable, StrategyError, UnknownStrategy
from .routers import meta
from .runner import EvaluationLoop
from .runtime import MIGRATION_LOCK_KEY, MIGRATIONS

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()  # type: ignore[call-arg]

    # Constructed, not connected: no request is made here. Reaching the archive at startup
    # would make this process's health depend on another module's, and there is nothing it
    # could usefully do with the answer at that moment anyway.
    async with (
        make_pool(
            settings.database_url,
            user=settings.database_user,
            client_id=settings.azure_client_id,
            client_secret=settings.azure_client_secret,
            tenant_id=settings.azure_tenant_id,
        ) as pool,
        http_client(settings.market_data_scope) as client,
    ):
        # One connection held for the whole of it: the advisory lock is session scoped, so
        # it has to be released on the connection that took it, and handing that connection
        # back to the pool in between would release it early.
        async with pool.acquire() as conn:
            async with advisory_lock(
                conn, MIGRATION_LOCK_KEY, wait=settings.migration_lock_wait_seconds
            ):
                log.info("bringing the database up to this image's revision")
                await migrate.run(MIGRATIONS)
            # Still checked, and for a narrower pair of accidents than the migration
            # itself: a migration that reported success without arriving, and an image
            # older than the schema it found.
            await schema_version.verify(conn, MIGRATIONS)

        app.state.settings = settings
        app.state.pool = pool
        app.state.archive = Archive(settings.market_data_url, client)

        # Started last, once everything a pass could need is already on the state. A
        # platform with no active watches starts and serves exactly the same way — zero is
        # a supported state, not a degraded one.
        loop = EvaluationLoop(
            pool, app.state.archive, interval_seconds=settings.evaluation_interval_seconds
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


async def _refused(request: Request, exc: StrategyError) -> JSONResponse:
    # 404 for a strategy this image does not carry, 502/504 for the archive, 422 for the
    # rest. The archive's two are told apart because a consumer's next move differs: one
    # is "try again", the other is "the request was wrong".
    if isinstance(exc, UnknownStrategy):
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
    """One assembled application, owning nothing that outlives it.

    A factory rather than a module-level object because `app.state` is where every
    dependency is held, and a single shared instance makes that state a global one test
    hands to the next.
    """
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

    for area in (meta,):
        app.include_router(area.router)

    # The tool surface, as a mounted ASGI application rather than a router: what the MCP
    # library builds is a Starlette app, not an `APIRouter`. `build_mcp_app` is handed the
    # application rather than its state because the state does not exist yet.
    from .mcp_app import ToolSurfaceAddress, build_mcp_app

    mcp_server, mcp_asgi = build_mcp_app(app)
    app.state.mcp_server = mcp_server
    app.mount("/mcp", mcp_asgi)

    # In front of both surfaces, and it has to be one layer rather than a dependency per
    # router: `/mcp` is a mounted ASGI application, so a `dependencies=` check could not
    # reach it and the rule would exist in two mechanisms that drift in one direction.
    # Added first, so it ends up *inside* the caller-access layer: that layer decides on
    # `/mcp` as written, and this one turns it into the path the router can match.
    app.add_middleware(ToolSurfaceAddress)
    app.add_middleware(CallerAccess, state=app.state)

    return app


# The ASGI entrypoint every deployment names — `uvicorn strategy.app:app` in the
# Dockerfile, in `scripts/dev.py` and in the README.
app = create_app()
