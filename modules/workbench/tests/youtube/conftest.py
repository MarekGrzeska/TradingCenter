"""Shared fixtures — chiefly the throwaway PostgreSQL the `db` tests run against, a container per session because the
schema is part of what is under test. The `--run-live` option and the Docker skip are the root conftest's."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import asyncpg
import pytest
from tc_runtime.db import asyncpg_dsn, sqlalchemy_url

from youtube_data.app import create_app
from youtube_data.config import Settings

# Emptied between tests so one test's rows are never another's premise. Named in full rather than left to CASCADE, so the
# statement says what it empties.
TABLES: tuple[str, ...] = (
    "candidates",
    "ignored_channels",
    "readings",
    "transcripts",
    "videos",
    "channels",
    "topics",
    "usage",
    "provider_state",
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

    from youtube_data.runtime import MIGRATIONS

    upgrade_to_head(MIGRATIONS, sqlalchemy_url(postgres_url))
    return postgres_url


# The seeded prompt is the migration's and stays; every other prompt is a test's and goes with the rows that read by it.
CLEAN = (
    f"TRUNCATE {', '.join(TABLES)}; "
    "DELETE FROM prompt_versions WHERE prompt_id IN (SELECT id FROM prompts WHERE NOT seeded); "
    "DELETE FROM prompts WHERE NOT seeded; "
    "DELETE FROM prompt_versions WHERE version > 1; "
    "UPDATE prompts SET name = 'Rynkowy', deleted_at = NULL WHERE seeded"
)


@pytest.fixture
async def db(migrated_url: str) -> AsyncIterator[asyncpg.Connection]:
    """A connection to the migrated database, with the tables emptied first."""
    conn = await asyncpg.connect(asyncpg_dsn(migrated_url))
    try:
        await conn.execute(CLEAN)
        yield conn
    finally:
        await conn.close()


@pytest.fixture
def settings() -> Settings:
    """What the application reads about itself, minus anything that reaches outward. The database URL is metadata only:
    a throwaway value satisfying Settings' rules, which `migrated_url` does not."""
    return Settings(
        database_url="postgresql://localhost:5432/test?sslmode=require",
        database_user="test-user",
        # A deployment's settings, so the real providers: the simulation is refused where DATABASE_USER is set.
        video_source="data_api",
        data_api_key="test-key",
        transcriber="gemini",
        gemini_api_key="test-key",
        analyser="openai",
        _env_file=None,
    )


@pytest.fixture
async def pool(migrated_url: str):
    """A pool over the migrated database, emptied first."""
    from tc_runtime.db import pool as make_pool

    async with make_pool(migrated_url, max_size=5) as created:
        async with created.acquire() as conn:
            await conn.execute(CLEAN)
        yield created


@pytest.fixture
def app():
    """A fresh application per test. A fixture rather than an import: while the module-level `app` was in scope, a test
    that forgot to ask for this one still found something to mutate."""
    return create_app()
