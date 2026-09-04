"""Shared fixtures — chiefly the throwaway PostgreSQL the `db` tests run against, a container per
session because the schema is part of what is under test. The `--run-live` option and the Docker skip are the
root conftest's, which pytest reads them from alone."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import asyncpg
import pytest
from tc_runtime.db import asyncpg_dsn, sqlalchemy_url

from social_data.app import create_app
from social_data.config import Settings

# Emptied between tests so one test's rows are never another's premise. TRUNCATE rather than
# re-migrating, and named in full rather than left to CASCADE, so the statement says what it empties.
TABLES: tuple[str, ...] = ("model_usage", "posts", "collection_state")


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """A URL to an empty PostgreSQL, alive for the session and gone afterwards."""
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:17-alpine", driver=None) as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def migrated_url(postgres_url: str) -> str:
    """The same database with the module's migrations applied — by running alembic, because a fixture
    that builds its own schema tests one no deployment will have. Synchronous: alembic calls `asyncio.run`."""
    from tc_runtime.migrate import upgrade_to_head

    from social_data.runtime import MIGRATIONS

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
def settings() -> Settings:
    """What the application reads about itself, minus anything that reaches outward. The database URL is
    metadata only: a throwaway value satisfying Settings' rules, which `migrated_url` does not."""
    return Settings(
        database_url="postgresql://localhost:5432/test?sslmode=require",
        database_user="test-user",
        _env_file=None,
    )


@pytest.fixture
async def pool(migrated_url: str):
    """A pool over the migrated database, emptied first — what `Ingest` takes."""
    from tc_runtime.db import pool as make_pool

    async with make_pool(migrated_url, max_size=5) as created:
        async with created.acquire() as conn:
            await conn.execute(f"TRUNCATE {', '.join(TABLES)}")
        yield created


@pytest.fixture
async def api(app, pool, settings):
    """The application wired to a real database, with nothing reaching outward. The lifespan is
    bypassed rather than run: it would start the collector, which would reach a third party."""
    import httpx

    app.state.pool = pool
    app.state.settings = settings
    app.state.enrichment = None

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://tests") as client:
        yield client


@pytest.fixture
async def tool_server(app, pool, settings):
    """The FastMCP server this module publishes, wired to a real database and built from the same
    application `create_app()` builds — a server assembled here would be a ceiling on nothing."""
    app.state.pool = pool
    app.state.settings = settings
    return app.state.mcp_server


@pytest.fixture
def app():
    """A fresh application per test. A fixture rather than an import: while the module-level `app` was in
    scope, a test that forgot to ask for this one still found something to mutate."""
    return create_app()
