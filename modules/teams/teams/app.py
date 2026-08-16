"""The published surface: FastAPI over the module.

Assembly only, same split as `agent/app.py` and `market_data/app.py`: the lifespan and
the routers mounted onto it. This is the skeleton — the lifespan brings the module's own
database to the revision it was built for and nothing else; the catalogue, run and
tool-server routers arrive in later changes, each mounted here the same way.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

# Root logger configuration, before anything else imports and starts logging. Nothing
# else sets a level or a destination — mirrors agent.app's and market_data.telemetry's
# reasoning: without this the module writes into the void, and a silent module looks
# exactly like an idle one.
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(levelname)-5.5s [%(name)s] %(message)s",
)

from fastapi import FastAPI

from . import migrate, schema_version
from .config import Settings
from .db import MIGRATION_LOCK_KEY, advisory_lock
from .db import pool as make_pool
from .openapi import require_response_fields
from .tools import ToolServer

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()  # type: ignore[call-arg]
    async with make_pool(
        settings.database_url,
        user=settings.database_user,
        client_id=settings.azure_client_id,
        client_secret=settings.azure_client_secret,
        tenant_id=settings.azure_tenant_id,
    ) as pool:
        # The database is brought to this image's revision here, before anything is
        # built on top of it and before a single request is served — a deployment
        # carries its own schema, and no operator stands between a merge and a working
        # module (`teams-database-connection`, "Moduł sam doprowadza bazę do rewizji,
        # dla której powstał").
        #
        # One connection held for the whole of it: the advisory lock is session scoped,
        # so it has to be released on the connection that took it, and handing that
        # connection back to the pool in between would release it early.
        async with pool.acquire() as conn:
            async with advisory_lock(
                conn, MIGRATION_LOCK_KEY, wait=settings.migration_lock_wait_seconds
            ):
                await migrate.run()
            # Still checked, and now for a narrower pair of accidents than before: a
            # migration that reported success without arriving, and an image older than
            # the schema it found (`schema_version.py`).
            await schema_version.verify(conn)

        # Built here, connected to nothing yet: the session opens on first use and the
        # tool list is read then. That is what keeps market-mcp off this module's start-up
        # path — a team assigning no tools never touches it, and the catalogue is served
        # whether or not it answers (specs/teams-tool-access, "Moduł startuje bez serwera
        # narzędzi"). The refusal a missing server earns belongs to starting a *run*.
        tools = ToolServer(settings)

        app.state.settings = settings
        app.state.pool = pool
        app.state.tools = tools
        try:
            yield
        finally:
            await tools.aclose()


app = FastAPI(
    title="TradingCenter · teams",
    description=(
        "Operator-defined teams of agents, saved to a catalogue and run by hand. A "
        "team's definition is data — a graph of roles and dependencies, versioned "
        "append-only — compiled to a run rather than written as code. This phase writes "
        "no order: a run ends in a recommendation kept in its trace, not a position "
        "(specs/teams-runs)."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# No CORS middleware here, and adding one would break the browser rather than help it —
# same reasoning as agent.app and market_data.app: App Service's own CORS layer answers
# the cross-origin preflight before Easy Auth would refuse it for carrying no
# credential. See infra/app-service.tf.

# `app.openapi` replaced with a wrapper rather than called once at import time — FastAPI
# caches whatever the wrapper returns on `app.openapi_schema`, so this runs once per
# process and every later `.openapi()` call (from `/openapi.json`, from `teams.openapi.
# document()`, from a test) reads the same augmented dict (`market_data.app`'s own
# comment explains the caching this relies on).
_routes_openapi = app.openapi


def _openapi_with_required_fields() -> dict:
    return require_response_fields(_routes_openapi())


app.openapi = _openapi_with_required_fields  # type: ignore[method-assign]


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
