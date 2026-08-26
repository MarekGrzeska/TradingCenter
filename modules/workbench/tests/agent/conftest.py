"""The conversation surface's own database fixtures. A PostgreSQL of its own rather than a second schema in
the teams one: the two chains own `alembic_version` separately, which is why production has two databases."""

from __future__ import annotations

from collections.abc import AsyncIterator

import asyncpg
import pytest
from tc_runtime.db import asyncpg_dsn

# Children before parents: `tool_calls` and `usage` both reference `messages`, and
# `chart_commands` and `chart_drawings` reference `sessions`.
TABLES = ("chart_drawings", "chart_commands", "tool_calls", "usage", "messages", "sessions")


@pytest.fixture(scope="session")
def postgres_url(agent_postgres_url: str) -> str:
    """This suite's name for its own empty container — see `migrated_url` below."""
    return agent_postgres_url


@pytest.fixture(scope="session")
def migrated_url(agent_migrated_url: str) -> str:
    """This suite's name for the conversation's database. The container and the migration are
    `tests/conftest.py`'s, because the process needs both databases and only that file sees both."""
    return agent_migrated_url


@pytest.fixture(scope="session")
async def seeded_prompt_revision_max_id(migrated_url: str) -> int:
    """Whatever id the migrations left `prompt_revisions` on, captured once right after they ran — so a
    later seeding migration needs no edit here, unlike a number written in by hand."""
    conn = await asyncpg.connect(asyncpg_dsn(migrated_url))
    try:
        return await conn.fetchval("SELECT max(id) FROM prompt_revisions")
    finally:
        await conn.close()


@pytest.fixture
async def db(
    migrated_url: str, seeded_prompt_revision_max_id: int
) -> AsyncIterator[asyncpg.Connection]:
    """A connection to the migrated database, with the tables emptied first. `prompt_revisions` is not in
    `TABLES`: the migrations themselves insert into it, and truncating would erase the seeds.

    Everything up to `seeded_prompt_revision_max_id` is those seeds, so dropping what follows undoes a
    previous test's own writes without reconstructing seeded text here."""
    conn = await asyncpg.connect(asyncpg_dsn(migrated_url))
    try:
        await conn.execute(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE")
        await conn.execute(
            "DELETE FROM prompt_revisions WHERE id > $1", seeded_prompt_revision_max_id
        )
        yield conn
    finally:
        await conn.close()


@pytest.fixture
async def pool(db: asyncpg.Connection, migrated_url: str) -> AsyncIterator[asyncpg.Pool]:
    """A pool over the same emptied database `db` connects to — `turn.py` takes a pool,
    not a bare connection, because a turn acquires twice (history, then the reply)."""
    created = await asyncpg.create_pool(asyncpg_dsn(migrated_url))
    try:
        yield created
    finally:
        await created.close()
