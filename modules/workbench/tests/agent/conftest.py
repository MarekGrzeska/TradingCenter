"""The conversation surface's own database fixtures.

A PostgreSQL of its own rather than a second schema in the teams one: the two chains own
`alembic_version` separately, which is the whole reason there are two databases in
production as well. Everything not about this database — the Docker probe, `--run-live`,
the environment a developer's machine has — is one copy in `tests/conftest.py`.
"""

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
    """This suite's name for the conversation's database. The container and the migration
    are `tests/conftest.py`'s, because the process needs both databases and only that file
    can see both."""
    return agent_migrated_url


@pytest.fixture(scope="session")
async def seeded_prompt_revision_max_id(migrated_url: str) -> int:
    """Whatever id the migrations themselves left `prompt_revisions` on, captured once
    right after they ran — so a later migration seeding another revision needs no edit
    here, unlike a number written in by hand that this file has already had to bump once."""
    conn = await asyncpg.connect(asyncpg_dsn(migrated_url))
    try:
        return await conn.fetchval("SELECT max(id) FROM prompt_revisions")
    finally:
        await conn.close()


@pytest.fixture
async def db(
    migrated_url: str, seeded_prompt_revision_max_id: int
) -> AsyncIterator[asyncpg.Connection]:
    """A connection to the migrated database, with the tables emptied first.

    `prompt_revisions` is not in `TABLES`: unlike every other table here, the
    migrations themselves insert into it, and `migrated_url` runs them once for the
    whole session. Blindly truncating it would erase the seeds a test asserting on
    their actual text depends on. Everything up to `seeded_prompt_revision_max_id` is
    those seeds — the only things ever written to a table nothing else has touched yet
    — so dropping everything after it undoes whatever a previous test's own
    `create_prompt_revision` calls added, without reconstructing seeded text here a
    second time.
    """
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
