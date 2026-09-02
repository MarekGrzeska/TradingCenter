"""The published surface: FastAPI over the door to Telegram. Only assembly lives here, and the order
inside the lifespan is what to read twice: the database is migrated before anything is served."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from tc_runtime import telemetry

# Above `from fastapi import ...` and not merely before `FastAPI(...)`: the auto-instrumentation
# patches the class attribute, and the import binds this module's name to the unpatched one. Nothing
# is quietened: `httpx`'s request line carries the bot token, and `redaction.py` exists to redact it.
telemetry.configure()

from fastapi import FastAPI
from tc_runtime import migrate, schema_version
from tc_runtime.db import advisory_lock
from tc_runtime.db import pool as make_pool

from . import mcp_app
from .binding import Watcher
from .bot_api import bot_api
from .caller_access import RECORD, CallerAccess
from .config import Settings
from .routers import bots, destinations, messages, meta, state
from .runtime import MIGRATION_LOCK_KEY, MIGRATIONS

log = logging.getLogger(__name__)



@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()  # type: ignore[call-arg]
    app.state.settings = settings

    async with (
        bot_api(settings.bot_api_base_url) as telegram,
        make_pool(
            settings.database_url,
            user=settings.database_user,
            client_id=settings.azure_client_id,
            client_secret=settings.azure_client_secret,
            tenant_id=settings.azure_tenant_id,
            max_size=settings.database_pool_size,
        ) as pool,
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
        app.state.telegram = telegram

        # After the migration and not before it: a bound destination is a write, and a write to a
        # schema this process does not know is not undone by a later error response.
        watcher = Watcher(pool, telegram)
        app.state.watcher = watcher
        await watcher.start()

        # The tool surface's session manager: a mounted application's lifespan is never run, so the
        # task group has to be started here or every tool call fails.
        async with mcp_app.tool_surface_session(app):
            log.info(
                "telegram-gateway is serving; creating bots is %s",
                "available" if settings.can_create_bots else "unavailable (no account session)",
            )
            try:
                yield
            finally:
                await watcher.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title="telegram-gateway",
        version="0.1.0",
        summary="The one door to Telegram — one notification, sent now, remembered by nobody.",
        lifespan=lifespan,
    )
    app.include_router(meta.router)
    app.include_router(state.router)
    app.include_router(messages.router)
    app.include_router(bots.router)
    app.include_router(destinations.router)

    server, tool_app = mcp_app.build_mcp_app(app)
    app.state.mcp_server = server
    app.mount(mcp_app.MOUNT_PATH, tool_app)

    # In front of the whole application, and in this order: the address fix runs before routing, and
    # the caller record before that, so nothing decides who may call after routing has begun.
    app.add_middleware(mcp_app.ToolSurfaceAddress)
    app.add_middleware(CallerAccess, state=app.state, record=RECORD)
    return app


app = create_app()
