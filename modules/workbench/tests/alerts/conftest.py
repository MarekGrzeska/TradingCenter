"""Shared fixtures — chiefly the throwaway PostgreSQL the `db` tests run against, a container per session because the
schema is part of what is under test. The `--run-live` option and the Docker skip are the root conftest's."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import asyncpg
import pytest
from tc_runtime.db import asyncpg_dsn, sqlalchemy_url

from alerts.app import create_app
from alerts.config import Settings

# Emptied between tests so one test's rows are never another's premise. Named in full rather than left to CASCADE, so the
# statement says what it empties.
TABLES: tuple[str, ...] = (
    "fires",
    "rule_checks",
    "rules",
    "events",
    "event_types",
    "draft_usage",
    "migrations_done",
)


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """A URL to an empty PostgreSQL, alive for the session and gone afterwards."""
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:17-alpine", driver=None) as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def migrated_url(postgres_url: str) -> str:
    """The same database with the package's migrations applied — by running alembic, because a fixture that builds its
    own schema tests one no deployment will have. Synchronous: alembic calls `asyncio.run`."""
    from tc_runtime.migrate import upgrade_to_head

    from alerts.runtime import MIGRATIONS

    upgrade_to_head(MIGRATIONS, sqlalchemy_url(postgres_url))
    return postgres_url


@pytest.fixture
async def db(migrated_url: str) -> AsyncIterator[asyncpg.Connection]:
    """A connection to the migrated database, with the tables emptied first."""
    conn = await asyncpg.connect(asyncpg_dsn(migrated_url))
    try:
        await conn.execute(f"TRUNCATE {', '.join(TABLES)} CASCADE")
        yield conn
    finally:
        await conn.close()


@pytest.fixture
def settings() -> Settings:
    """What the application reads about itself. The database URL is metadata only: a throwaway value satisfying
    Settings' rules, which `migrated_url` does not."""
    return Settings(
        database_url="postgresql://localhost:5432/test?sslmode=require",
        database_user="test-user",
        _env_file=None,
    )


@pytest.fixture
async def pool(migrated_url: str):
    """A pool over the migrated database, emptied first."""
    from tc_runtime.db import pool as make_pool

    async with make_pool(migrated_url, max_size=5) as created:
        async with created.acquire() as conn:
            await conn.execute(f"TRUNCATE {', '.join(TABLES)} CASCADE")
        yield created


@pytest.fixture
def app():
    """A fresh application per test. A fixture rather than an import: while the module-level `app` was in scope, a test
    that forgot to ask for this one still found something to mutate."""
    return create_app()


def _idle_clock(pool, settings, tools):
    """The clock the application would have, not running: a route may wake it, and a test drives its ticks itself."""
    from tc_runtime.liveness import LoopHeartbeat

    from alerts.clock import Clock

    return Clock(pool, settings, tools, LoopHeartbeat("clock", expected_seconds=5))


@pytest.fixture
def tools():
    from .builders import FakeTools

    return FakeTools()


@pytest.fixture
def drafter():
    from .builders import FakeDrafter

    return FakeDrafter()


@pytest.fixture
def door():
    from .builders import FakeGateway

    return FakeGateway()


@pytest.fixture
async def api(app, pool, settings, tools, door, drafter):
    """The application as the terminal reaches it — no identity required, as locally — over the migrated database."""
    import httpx

    app.state.pool = pool
    app.state.settings = settings
    app.state.tools = tools
    app.state.gateway = door
    app.state.drafter = drafter
    app.state.clock = _idle_clock(pool, settings, tools)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://tests") as client:
        yield client


@pytest.fixture
async def inside(app, pool, settings, tools, door, drafter):
    """The same application as another package of the process reaches it."""
    import httpx
    from tc_runtime.caller_access import in_process

    app.state.pool = pool
    app.state.settings = settings
    app.state.tools = tools
    app.state.gateway = door
    app.state.drafter = drafter
    app.state.clock = _idle_clock(pool, settings, tools)
    transport = httpx.ASGITransport(app=in_process(app, "the youtube archive"))
    async with httpx.AsyncClient(transport=transport, base_url="http://tests") as client:
        yield client
