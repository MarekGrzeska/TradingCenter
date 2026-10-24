"""Shared fixtures — chiefly the throwaway PostgreSQL the `db` tests run against, a container per session because the
schema is part of what is under test. The `--run-live` option and the Docker skip are the root conftest's."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import asyncpg
import pytest
from tc_runtime.db import asyncpg_dsn, sqlalchemy_url

from strategies.app import create_app
from strategies.config import Settings

# Emptied between tests so one test's rows are never another's premise. Named in full rather than left to CASCADE, so the
# statement says what it empties.
TABLES: tuple[str, ...] = ("run_trades", "runs", "strategy_revisions", "strategies")


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

    from strategies.runtime import MIGRATIONS

    upgrade_to_head(MIGRATIONS, sqlalchemy_url(postgres_url))
    return postgres_url


@pytest.fixture
async def db(migrated_url: str) -> AsyncIterator[asyncpg.Connection]:
    """A connection to the migrated database, with the tables emptied first."""
    conn = await asyncpg.connect(asyncpg_dsn(migrated_url))
    try:
        await conn.execute(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE")
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
        _env_file=None,  # type: ignore[call-arg]
    )


@pytest.fixture
def app():
    return create_app()
