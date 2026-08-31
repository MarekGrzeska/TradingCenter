"""The teams surface's own database fixtures. A PostgreSQL of its own rather than a second schema in the
conversation's: the two chains own `alembic_version` separately, which is why production has two databases."""

from __future__ import annotations

from collections.abc import AsyncIterator

import asyncpg
import pytest
from tc_runtime.db import asyncpg_dsn

# Children before parents, the same convention agent's own TABLES follows. `team_memories` references both
# `teams` and `runs`, so it goes before either.
TABLES: tuple[str, ...] = (
    "trades",
    "usage",
    "tool_calls",
    "schedule_fires",
    "team_memories",
    "run_steps",
    "runs",
    "schedules",
    "triggers",
    "team_layouts",
    "team_revisions",
    "teams",
)


@pytest.fixture(scope="session")
def postgres_url(teams_postgres_url: str) -> str:
    """This suite's name for its own empty container — see `migrated_url` below."""
    return teams_postgres_url


@pytest.fixture(scope="session")
def migrated_url(teams_migrated_url: str) -> str:
    """This suite's name for the teams database — see the conversation suite's twin."""
    return teams_migrated_url


@pytest.fixture
async def db(migrated_url: str) -> AsyncIterator[asyncpg.Connection]:
    """A connection to the migrated database, with any owned tables emptied first."""
    conn = await asyncpg.connect(asyncpg_dsn(migrated_url))
    try:
        if TABLES:
            await conn.execute(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE")
        yield conn
    finally:
        await conn.close()


@pytest.fixture
async def pool(db: asyncpg.Connection, migrated_url: str) -> AsyncIterator[asyncpg.Pool]:
    """A pool over the same emptied database `db` connects to."""
    created = await asyncpg.create_pool(asyncpg_dsn(migrated_url))
    try:
        yield created
    finally:
        await created.close()
