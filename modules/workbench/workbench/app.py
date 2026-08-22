"""The published surface: one FastAPI over both halves of the operator's workbench.

Assembly only. Each surface says which routers it publishes and what its routes read
(`agent/surface.py`, `teams/surface.py`); this file builds the application, runs the one
lifespan both of them live in, and is the only module that imports all three packages
(`tests/test_layering.py`).

**The lifespan is all-or-nothing on purpose.** Two databases are brought to this image's
revision before a single request is served, each under its own advisory lock. There is no
mode where the process serves the conversation and calls the teams catalogue unavailable:
a half-state nobody exercises is worse than a failure that shows, and the deploy probe
reaches the process rather than the control plane, so a process that answers is itself the
proof that both chains are at head.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

# Root logger configuration, before anything else imports and starts logging. Nothing else
# sets a level or a destination — mirrors market_data.telemetry's reasoning: without this
# the process writes into the void, and a silent process looks exactly like an idle one.
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(levelname)-5.5s [%(name)s] %(message)s",
)

from fastapi import FastAPI
from tc_runtime import migrate, schema_version
from tc_runtime.db import advisory_lock
from tc_runtime.db import pool as make_pool

import agent.surface
import teams.surface
from agent.models_catalogue import ModelCatalogue as AgentCatalogue
from agent.provider import OpenAIProvider as AgentProvider
from agent.runtime import MIGRATION_LOCK_KEY as AGENT_LOCK_KEY
from agent.runtime import MIGRATIONS as AGENT_MIGRATIONS
from agent.tools import ToolServerRegistry
from teams import store as teams_store
from teams.models_catalogue import ModelCatalogue as TeamsCatalogue
from teams.openapi import require_response_fields
from teams.provider import OpenAIProvider as TeamsProvider
from teams.runner import RunRegistry
from teams.runtime import MIGRATION_LOCK_KEY as TEAMS_LOCK_KEY
from teams.runtime import MIGRATIONS as TEAMS_MIGRATIONS
from teams.scheduler import Clock
from teams.tools import ToolServerRegistry as TeamsToolServerRegistry

from .config import Settings
from .team_tools import LocalTeamsTools

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()  # type: ignore[call-arg]
    conversation_settings = settings.for_conversation()
    teams_settings = settings.for_teams()

    # Constructed, not connected: a session opens on the first turn that wants a tool.
    # Reaching market-data at startup would make this process's health depend on another
    # module's, and its whole answer to that module being down is to run without its tools.
    team_tools = LocalTeamsTools(
        app, operator_identity_optional=not settings.require_authenticated_principal
    )
    conversation_tools = ToolServerRegistry.from_settings(
        conversation_settings, local_sources=[team_tools]
    )

    async with (
        make_pool(
            conversation_settings.database_url,
            user=conversation_settings.database_user,
            client_id=conversation_settings.azure_client_id,
            client_secret=conversation_settings.azure_client_secret,
            tenant_id=conversation_settings.azure_tenant_id,
        ) as conversation_pool,
        make_pool(
            teams_settings.database_url,
            user=teams_settings.database_user,
            client_id=teams_settings.azure_client_id,
            client_secret=teams_settings.azure_client_secret,
            tenant_id=teams_settings.azure_tenant_id,
        ) as teams_pool,
    ):
        # Built here rather than beside the conversation's, because one of the sources it
        # holds is served by this process and reads the teams database directly. Announcing
        # those tools does not touch the pool — the descriptors are constants — but calling
        # them does, and this is the first point where there is a pool to give.
        teams_tool_servers = TeamsToolServerRegistry.from_settings(
            teams_settings, pool=teams_pool
        )

        # The `try` opens before the schema checks, not after them: `ToolServer.__init__`
        # already holds a credential when a scope is configured, and a refused start is
        # exactly the path that would otherwise leak it.
        try:
            # Each database is brought to this image's revision before anything is built
            # on top of it — a deployment carries its own schema, and no operator stands
            # between a merge and a working process.
            #
            # One connection held for the whole of each: the advisory lock is session
            # scoped, so it has to be released on the connection that took it, and handing
            # that connection back to the pool in between would release it early. Two
            # locks with two keys, on two databases: a process waiting for the
            # conversation's chain never holds up the teams one.
            await _migrate(
                conversation_pool,
                AGENT_MIGRATIONS,
                AGENT_LOCK_KEY,
                wait=conversation_settings.migration_lock_wait_seconds,
                label="conversation",
            )
            await _migrate(
                teams_pool,
                TEAMS_MIGRATIONS,
                TEAMS_LOCK_KEY,
                wait=teams_settings.migration_lock_wait_seconds,
                label="teams",
            )

            async with teams_pool.acquire() as conn:
                # A run lives in the process that started it, so anything still `running`
                # in the database belongs to a process that is gone — closed here, before a
                # route can report it as work in progress that nobody is doing
                # (specs/teams-runs).
                orphans = await teams_store.fail_unfinished_runs(
                    conn, reason="the module restarted while this run was in progress"
                )
            if orphans:
                log.warning(
                    "closed %d run(s) left in progress by an earlier process: %s",
                    len(orphans),
                    orphans,
                )

            app.state.settings = settings
            app.state.agent = agent.surface.State(
                settings=conversation_settings,
                pool=conversation_pool,
                catalogue=AgentCatalogue.from_settings(conversation_settings),
                provider=AgentProvider(conversation_settings),
                tool_server=conversation_tools,
            )
            app.state.teams = teams.surface.State(
                settings=teams_settings,
                pool=teams_pool,
                # Built once, from settings that were already refused if a model carried
                # no rate or a duplicate id (`config.py`) — so nothing downstream
                # re-checks either.
                catalogue=TeamsCatalogue.from_settings(teams_settings),
                provider=TeamsProvider(teams_settings),
                tools=teams_tool_servers,
                runs=RunRegistry(),
            )

            # Started last, once everything a fire could possibly need is already on
            # `app.state` — a schedule due the instant this process comes up MUST see the
            # same catalogue, provider and tool session a route would. Stopped first in
            # `finally`, before the tool session it may still be mid-call against.
            clock = Clock(
                teams_pool,
                catalogue=app.state.teams.catalogue,
                provider=app.state.teams.provider,
                tool_registry=teams_tool_servers,
                settings=teams_settings,
                registry=app.state.teams.runs,
            )
            app.state.teams.clock = clock
            clock.start()
            try:
                yield
            finally:
                await clock.aclose()
        finally:
            await teams_tool_servers.aclose()
            await conversation_tools.aclose()


async def _migrate(pool, migrations, lock_key: int, *, wait: float, label: str) -> None:
    """One chain, on its own database, under its own key.

    The label is in the message rather than in a second copy of this function: a start-up
    that fails here has to say *which* of the two databases it was, and "the database" was
    unambiguous only while there was one.
    """
    async with pool.acquire() as conn:
        async with advisory_lock(conn, lock_key, wait=wait):
            log.info("%s: bringing the database up to this image's revision", label)
            await migrate.run(migrations)
        # Still checked, and for a narrower pair of accidents than the migration itself: a
        # migration that reported success without arriving, and an image older than the
        # schema it found (`schema_version.py`).
        await schema_version.verify(conn, migrations)


app = FastAPI(
    title="TradingCenter · workbench",
    description=(
        "The operator's conversation with a model, and the teams of agents they compose "
        "and run — one process over two schemas. The conversation persists its sessions "
        "and transcripts; a team's definition is data, versioned append-only, compiled to "
        "a run rather than written as code. Each model call prices itself at the moment "
        "it is written, against this process's own rate configuration, never recomputed "
        "later. Read-only tools over the candle archive reach market-data; the tools that "
        "build and run teams are a layer in this process."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# No CORS middleware here, and adding one would break the browser rather than help it —
# same reasoning as market_data.app: App Service's own CORS layer answers the cross-origin
# preflight before Easy Auth would refuse it for carrying no credential.
# See infra/app-service.tf.

# `app.openapi` replaced with a wrapper rather than called once at import time — FastAPI
# caches whatever the wrapper returns on `app.openapi_schema`, so this runs once per
# process and every later `.openapi()` call reads the same augmented dict.
_routes_openapi = app.openapi


def _openapi_with_required_fields() -> dict:
    return require_response_fields(_routes_openapi())


app.openapi = _openapi_with_required_fields  # type: ignore[method-assign]


@app.get("/health")
async def health() -> dict[str, str]:
    """The one entry that answers without a credential — excluded from Easy Auth in
    `infra/app-service.tf` and read by the deploy probe. It says the process answers and
    nothing else: no count of sessions, no team, no operator."""
    return {"status": "ok"}


agent.surface.include(app)
teams.surface.include(app)
