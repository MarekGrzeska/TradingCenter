"""Shared fixtures — chiefly the throwaway PostgreSQL the `db` tests run against, a container per session
because the schema is part of what is under test. The Docker skip is the root conftest's."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import asyncpg
import httpx
import pytest
from tc_runtime.db import asyncpg_dsn, sqlalchemy_url

from strategy.app import create_app
from strategy.config import Settings

# Emptied between tests so one test's rows are never another's premise; TRUNCATE rather than re-migrating, since the
# schema is the same for every test. One statement naming every table, so the foreign keys need no CASCADE.
TABLES = (
    "decisions",
    "watches",
    "parameter_sets",
    "backtest_runs",
    "strategy_revisions",
    "strategy_definitions",
)


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """A URL to an empty PostgreSQL, alive for the session and gone afterwards."""
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:17-alpine", driver=None) as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def migrated_url(postgres_url: str) -> str:
    """The same database with this module's migrations applied — by running alembic, because a fixture that
    builds its own schema tests one no deployment will have. Synchronous: alembic calls `asyncio.run`."""
    from tc_runtime.migrate import upgrade_to_head

    from strategy.runtime import MIGRATIONS

    upgrade_to_head(MIGRATIONS, sqlalchemy_url(postgres_url))
    return postgres_url


@pytest.fixture
async def db(migrated_url: str) -> AsyncIterator[asyncpg.Connection]:
    """A connection to the migrated database, with the tables emptied first."""
    conn = await asyncpg.connect(asyncpg_dsn(migrated_url))
    try:
        await conn.execute(f"TRUNCATE {', '.join(TABLES)}")
        yield conn
    finally:
        await conn.close()


@pytest.fixture
async def pool(migrated_url: str):
    from tc_runtime.db import pool as make_pool

    async with make_pool(migrated_url, max_size=5) as created:
        async with created.acquire() as conn:
            await conn.execute(f"TRUNCATE {', '.join(TABLES)}")
        yield created


@pytest.fixture
def settings() -> Settings:
    """What the application reads about itself, minus anything that reaches outward. The database URL is
    metadata only: a throwaway value satisfying Settings' rules, which `migrated_url` does not."""
    return Settings(
        database_url="postgresql://localhost:5432/test?sslmode=require",
        database_user="test-user",
        _env_file=None,
    )


@pytest.fixture
def app():
    """A fresh application per test, so no test's `app.state` survives into the next."""
    return create_app()


@pytest.fixture
async def api(app, pool, settings):
    """The app wired to a real database, with the lifespan bypassed: it would migrate again and start the
    loop, which would reach an archive that is not there."""
    app.state.pool = pool
    app.state.settings = settings

    # `raise_app_exceptions=False` so the app's own error handling is what the test sees.
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://strategy.test") as client:
        yield client
