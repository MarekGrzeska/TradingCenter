"""The published surface: one FastAPI over both halves of the workbench and the four packages mounted under them,
assembly only. The lifespan is all-or-nothing, so a process that answers the deploy probe has already brought six
databases to this image's revision."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager, nullcontext

from tc_runtime import telemetry

# The candle stream, kept out of the trace: every frame `/market/ws/candles` sends was one dependency row, a
# quarter-million in two weeks. The instrumentor reads this once, from the environment, so it is here — before
# `configure` — and not in the package, which does not know its own mount.
UNTRACED_URLS = "/market/ws/candles"
os.environ.setdefault("OTEL_PYTHON_FASTAPI_EXCLUDED_URLS", UNTRACED_URLS)

# Above `from fastapi import ...` and not merely before `FastAPI(...)`: the auto-instrumentation patches the class
# attribute, and the import binds this module's name to the unpatched one. Logging always; Application Insights only
# with a connection string. Until 5 September 2026 this process configured logging alone, so the loop gauges the two
# archives register (`liveness.register_metrics`) were never exported and both loop alerts went without data.
telemetry.configure(quiet=("httpx", "httpcore", "urllib3"))

from fastapi import FastAPI
from starlette.routing import Mount
from tc_entra_auth import EdgeAuth
from tc_runtime import migrate, schema_version
from tc_runtime.db import advisory_lock
from tc_runtime.db import pool as make_pool
from tc_runtime.openapi import require_response_fields

import agent.surface
import alerts.app
import market_data.app
import polymarket_data.app
import social_data.app
import teams.surface
import telegram_gateway.app
import youtube_data.app
from agent import store as agent_store
from agent.models_catalogue import ModelCatalogue as AgentCatalogue
from agent.provider import OpenAIProvider as AgentProvider
from agent.runtime import MIGRATION_LOCK_KEY as AGENT_LOCK_KEY
from agent.runtime import MIGRATIONS as AGENT_MIGRATIONS
from agent.tools import ToolServerRegistry
from teams import store as teams_store
from teams.models_catalogue import ModelCatalogue as TeamsCatalogue
from teams.provider import OpenAIProvider as TeamsProvider
from teams.runner import RunRegistry
from teams.runtime import MIGRATION_LOCK_KEY as TEAMS_LOCK_KEY
from teams.runtime import MIGRATIONS as TEAMS_MIGRATIONS
from teams.scheduler import Clock
from teams.tools import ToolServerRegistry as TeamsToolServerRegistry

from . import model_successors
from .assembly import mount_package
from .config import Settings, alerts_enabled, youtube_enabled
from .edge import edge_config, edge_provider
from .local_tools import ConversationLocalTools, TeamsLocalTools
from .root_access import RootCallers
from .team_tools import LocalTeamsTools
from .telegram_client import telegram_client

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()  # type: ignore[call-arg]
    conversation_settings = settings.for_conversation()
    teams_settings = settings.for_teams()
    polymarket_settings = settings.for_polymarket()
    social_settings = settings.for_social()
    market_settings = settings.for_market()
    telegram_settings = settings.for_telegram()
    youtube_settings = settings.for_youtube() if YOUTUBE_MOUNTED else None
    alerts_settings = settings.for_alerts() if ALERTS_MOUNTED else None
    # Each package's tools, called as functions: the server its own `/mcp` mounts, minus the transport. The
    # archive's eleven were the first tools this process ever called, over the network; they are the last to move in.
    polymarket_tools = ConversationLocalTools("polymarket-data", polymarket_app.state.mcp_server)
    social_tools = ConversationLocalTools("social-data", social_app.state.mcp_server)
    market_tools = ConversationLocalTools("market-data", market_app.state.mcp_server)
    telegram_tools = ConversationLocalTools("telegram-gateway", telegram_app.state.mcp_server)
    youtube_tools = (
        None
        if youtube_app is None
        else ConversationLocalTools("youtube-data", youtube_app.state.mcp_server)
    )

    # Constructed, not connected: a session opens on the first turn that wants a tool. Reaching trading-mcp at startup
    # would make this process's health depend on another module's, whose answer is to run without its tools.
    team_tools = LocalTeamsTools(
        app, operator_identity_optional=not settings.require_authenticated_principal
    )
    conversation_tools = ToolServerRegistry.from_settings(
        conversation_settings,
        local_sources=[
            team_tools,
            market_tools,
            polymarket_tools,
            social_tools,
            telegram_tools,
            *([] if youtube_tools is None else [youtube_tools]),
        ],
    )

    async with (
        make_pool(
            conversation_settings.database_url,
            user=conversation_settings.database_user,
            client_id=conversation_settings.azure_client_id,
            client_secret=conversation_settings.azure_client_secret,
            tenant_id=conversation_settings.azure_tenant_id,
            max_size=settings.database_pool_size,
        ) as conversation_pool,
        make_pool(
            teams_settings.database_url,
            user=teams_settings.database_user,
            client_id=teams_settings.azure_client_id,
            client_secret=teams_settings.azure_client_secret,
            tenant_id=teams_settings.azure_tenant_id,
            max_size=settings.database_pool_size,
        ) as teams_pool,
        # A mounted application's lifespan is never run, so each package's pool, migration, loop and
        # tool session are entered here, beside this process's own two. The door to Telegram first: the post
        # archive's first pass may already have something to say.
        telegram_gateway.app.serving(telegram_app, telegram_settings),
        # After the door, before every package that publishes: what an archive announces at start has to find the
        # rules already there. Entered only when mounted, like the YouTube archive below.
        (
            alerts.app.serving(alerts_app, alerts_settings)
            if alerts_app is not None and alerts_settings is not None
            else nullcontext()
        ),
        telegram_client(telegram_app, "the post archive") as social_telegram,
        polymarket_data.app.serving(polymarket_app, polymarket_settings),
        social_data.app.serving(social_app, social_settings, telegram=social_telegram),
        # The archive's migration may wait on an index over the candle table, and its ingest opens a subscription
        # per tracked pair the moment it starts.
        market_data.app.serving(market_app, market_settings),
        # Entered only when mounted: with no database configured this is a block that does nothing, and the start-up
        # log line is what says why.
        (
            telegram_client(telegram_app, "the YouTube archive")
            if youtube_app is not None
            else nullcontext(None)
        ) as youtube_telegram,
        (
            youtube_data.app.serving(youtube_app, youtube_settings, telegram=youtube_telegram)
            if youtube_app is not None and youtube_settings is not None
            else nullcontext()
        ),
    ):
        # Built here rather than beside the conversation's, because one of its sources is served by this process and
        # reads the teams database directly: announcing needs no pool, calling does, and this is the first point with one.
        teams_tool_servers = TeamsToolServerRegistry.from_settings(
            teams_settings, pool=teams_pool
        )
        teams_tool_servers.local["polymarket-data"] = TeamsLocalTools(
            "polymarket-data", polymarket_app.state.mcp_server
        )
        teams_tool_servers.local["social-data"] = TeamsLocalTools(
            "social-data", social_app.state.mcp_server
        )
        teams_tool_servers.local["market-data"] = TeamsLocalTools(
            "market-data", market_app.state.mcp_server
        )
        teams_tool_servers.local["telegram-gateway"] = TeamsLocalTools(
            "telegram-gateway", telegram_app.state.mcp_server
        )
        if youtube_app is not None:
            teams_tool_servers.local["youtube-data"] = TeamsLocalTools(
                "youtube-data", youtube_app.state.mcp_server
            )

        # The `try` opens before the schema checks, not after: `ToolServer.__init__` already holds a credential when a
        # scope is configured, and a refused start is exactly the path that would otherwise leak it.
        try:
            # Each database is brought to this image's revision before anything is built on it. One
            # connection held throughout each: the advisory lock is session scoped. Two locks, two keys.
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
                # A run lives in the process that started it, so anything still `running` in the database belongs to a
                # process that is gone — closed here, before a route can report work nobody is doing.
                orphans = await teams_store.fail_unfinished_runs(
                    conn, reason="the module restarted while this run was in progress"
                )
            if orphans:
                log.warning(
                    "closed %d run(s) left in progress by an earlier process: %s",
                    len(orphans),
                    orphans,
                )

            # Built once, from settings already refused if a model carried no rate or a duplicate id, so nothing
            # downstream re-checks either.
            agent_catalogue = AgentCatalogue.from_settings(conversation_settings)
            teams_catalogue = TeamsCatalogue.from_settings(teams_settings)
            async with conversation_pool.acquire() as conn:
                moved_sessions = await agent_store.move_sessions_to_successors(
                    conn,
                    model_successors.applicable({entry.id for entry in agent_catalogue.entries()}),
                )
            async with teams_pool.acquire() as conn:
                moved_revisions = await teams_store.move_revisions_to_successors(
                    conn, model_successors.applicable(teams_catalogue.ids())
                )
            if moved_sessions or moved_revisions:
                log.warning(
                    "moved %d session(s) and %d team revision(s) off retired models to their successors",
                    moved_sessions,
                    moved_revisions,
                )

            app.state.settings = settings
            app.state.edge = edge_config(settings)
            app.state.agent = agent.surface.State(
                settings=conversation_settings,
                pool=conversation_pool,
                catalogue=agent_catalogue,
                provider=AgentProvider(conversation_settings),
                tool_server=conversation_tools,
            )
            app.state.teams = teams.surface.State(
                settings=teams_settings,
                pool=teams_pool,
                catalogue=teams_catalogue,
                provider=TeamsProvider(teams_settings),
                tools=teams_tool_servers,
                runs=RunRegistry(),
            )

            # Started last, once everything a fire could need is on `app.state` — a schedule due the instant this
            # process comes up MUST see what a route would. Stopped first, before the tool session it may be mid-call against.
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
    """One chain, on its own database, under its own key. The label is in the message rather than in a
    second copy of this function: a start-up that fails here has to say which of the two databases it was."""
    async with pool.acquire() as conn:
        async with advisory_lock(conn, lock_key, wait=wait):
            log.info("%s: bringing the database up to this image's revision", label)
            await migrate.run(migrations)
        # Still checked, and for a narrower pair of accidents than the migration itself: a migration that reported
        # success without arriving, and an image older than the schema it found.
        await schema_version.verify(conn, migrations)


app = FastAPI(
    title="TradingCenter · workbench",
    description=(
        "The operator's conversation with a model, and the teams of agents they compose "
        "and run — one process over two schemas. The conversation persists its sessions "
        "and transcripts; a team's definition is data, versioned append-only, compiled to "
        "a run rather than written as code. Each model call prices itself at the moment "
        "it is written, against this process's own rate configuration, never recomputed "
        "later. The tools that build and run teams are a layer in this process, and so are "
        "the three archives it serves — the candle archive under /market, prediction markets "
        "under /polymarket, and posts with what a model made of them under /social — and "
        "the one door to Telegram under /telegram."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# No CORS middleware here, and adding one would break the browser rather than help it: App Service's own CORS layer
# answers the cross-origin preflight before Easy Auth would refuse it for carrying no credential.

# `app.openapi` replaced with a wrapper rather than called once at import: FastAPI caches whatever the wrapper returns,
# so this runs once per process and every later call reads the same augmented dict.
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

# Each archive whole — its routers, its `/openapi.json`, its `/mcp`, its caller record — under one prefix.
polymarket_app = polymarket_data.app.create_app()
mount_package(app, "/polymarket", polymarket_app)
social_app = social_data.app.create_app()
mount_package(app, "/social", social_app)
# The candle archive, whole: its REST contract, its `/mcp`, and the one WebSocket this process serves —
# `/market/ws/candles`, outside Easy Auth and behind the archive's own one-time ticket.
market_app = market_data.app.create_app()
mount_package(app, "/market", market_app)
# The door to Telegram, whole: sending, its two tools, and the bots and destinations only the operator's `az` reaches.
telegram_app = telegram_gateway.app.create_app()
mount_package(app, "/telegram", telegram_app)

# The YouTube archive, whole, and only when its database is configured: absent is a working configuration, and a
# package mounted without a database would be the half-state `workbench-process` refuses. Decided here, at import,
# because a mount is the one thing the lifespan cannot add afterwards.
YOUTUBE_MOUNTED = youtube_enabled()
youtube_app = youtube_data.app.create_app() if YOUTUBE_MOUNTED else None
if youtube_app is not None:
    mount_package(app, "/youtube", youtube_app)
else:
    log.info("the YouTube archive is not part of this process: YOUTUBE_DATABASE_URL is not set")

# The alerts package, whole, and only when its database is configured — for the reason the YouTube archive is: a
# package mounted without a database is the half-state `workbench-process` refuses.
ALERTS_MOUNTED = alerts_enabled()
alerts_app = alerts.app.create_app() if ALERTS_MOUNTED else None
if alerts_app is not None:
    mount_package(app, "/alerts", alerts_app)
else:
    log.info("the alerts package is not part of this process: ALERTS_DATABASE_URL is not set")

# After every mount, so the prefixes it lets through to each package's own record are all of them.
app.add_middleware(
    RootCallers,
    state=app.state,
    package_prefixes=frozenset(route.path for route in app.routes if isinstance(route, Mount)),
)
# Last, so outermost: it settles who is calling before any record reads it. A no-op unless SERVER_MODE.
app.add_middleware(EdgeAuth, config=edge_provider(app))
