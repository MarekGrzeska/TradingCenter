"""Migrating at startup, and the lock that keeps two processes from doing it at once."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from urllib.parse import urlparse, urlunparse

import asyncpg
import pytest
from tc_runtime.db import advisory_lock, asyncpg_dsn, sqlalchemy_url
from tc_runtime.db import pool as make_pool
from tc_runtime.migrate import run
from tc_runtime.schema_version import applied_heads, expected_heads

from agent.runtime import MIGRATION_LOCK_KEY, MIGRATIONS


@pytest.fixture
async def empty_database_url(postgres_url: str) -> AsyncIterator[str]:
    """A database in the session's container that no migration has touched.

    `migrated_url` is session scoped and runs the migrations once for everything that
    asks for it, so a test needing an *unmigrated* database cannot share it — and cannot
    rely on running before it either. A fresh logical database costs one statement.
    """
    name = f"empty_{uuid.uuid4().hex[:12]}"
    admin = await asyncpg.connect(asyncpg_dsn(postgres_url))
    try:
        await admin.execute(f'CREATE DATABASE "{name}"')
    finally:
        await admin.close()

    parsed = urlparse(postgres_url)
    yield urlunparse(parsed._replace(path=f"/{name}"))

    admin = await asyncpg.connect(asyncpg_dsn(postgres_url))
    try:
        await admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
    finally:
        await admin.close()


@pytest.mark.db
async def test_an_empty_database_is_brought_to_head(empty_database_url: str) -> None:
    conn = await asyncpg.connect(asyncpg_dsn(empty_database_url))
    try:
        assert await applied_heads(conn) == set()

        await run(MIGRATIONS, sqlalchemy_url(empty_database_url))

        assert await applied_heads(conn) == expected_heads(MIGRATIONS)
    finally:
        await conn.close()


@pytest.mark.db
async def test_a_database_already_at_head_is_left_alone(migrated_url: str) -> None:
    conn = await asyncpg.connect(asyncpg_dsn(migrated_url))
    try:
        before = await conn.fetchval("SELECT max(id) FROM prompt_revisions")

        await run(MIGRATIONS, sqlalchemy_url(migrated_url))

        # `prompt_revisions` is the one table the migrations themselves write to, so a
        # migration that ran a second time would show up here as a duplicated seed.
        assert await conn.fetchval("SELECT max(id) FROM prompt_revisions") == before
    finally:
        await conn.close()


@pytest.mark.db
async def test_the_account_trace_migration_comes_back_down_over_a_row_it_forbids(
    empty_database_url: str,
) -> None:
    """`0011`'s downgrade is the one that cannot simply undo itself: it puts `NOT NULL` back
    on a column it allowed nulls into, and `unknown` out of a `CHECK` a row may be sitting
    on. Both are impossible while such a row exists, so the downgrade deletes them first —
    a real loss, named in the migration, and untested until here."""
    from alembic import command
    from tc_runtime.migrate import alembic_config

    # The same Config the module's own startup upgrade builds, so this walks the real
    # chain. In a thread because alembic's env.py drives its async engine with
    # `asyncio.run`, which refuses to nest inside this test's own loop.
    config = alembic_config(MIGRATIONS, sqlalchemy_url(empty_database_url))
    await asyncio.to_thread(command.upgrade, config, "head")

    conn = await asyncpg.connect(asyncpg_dsn(empty_database_url))
    try:
        session_id = await conn.fetchval(
            "INSERT INTO sessions (owner_principal, current_model_id) "
            "VALUES ('op-1', 'm') RETURNING id"
        )
        await conn.execute(
            "INSERT INTO tool_calls (session_id, message_id, round_index, position, "
            "tool_name, arguments, outcome, result_text, duration_ms) "
            "VALUES ($1, NULL, 0, 0, 'place_order', '{}'::jsonb, 'unknown', 'sent', 0)",
            session_id,
        )

        await asyncio.to_thread(command.downgrade, config, "0010")

        assert await conn.fetchval("SELECT count(*) FROM tool_calls") == 0
        assert await conn.fetchval(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name = 'tool_calls' AND column_name = 'message_id'"
        ) == "NO"

        # And back up again, because a downgrade nobody can reverse is a one-way door.
        await asyncio.to_thread(command.upgrade, config, "head")
        assert await applied_heads(conn) == expected_heads(MIGRATIONS)
    finally:
        await conn.close()


@pytest.mark.db
async def test_only_one_of_two_processes_migrates(empty_database_url: str) -> None:
    """Two starts against one empty database, racing the way two App Service instances do.

    Each takes its own connection, as two processes would; the lock lives in the database,
    which is the whole reason it works across them.
    """
    migrated: list[str] = []

    async def start(name: str) -> None:
        async with (
            make_pool(empty_database_url, min_size=1, max_size=1) as pool,
            pool.acquire() as conn,
            advisory_lock(conn, MIGRATION_LOCK_KEY, wait=60.0, poll=0.05),
        ):
            if await applied_heads(conn) != expected_heads(MIGRATIONS):
                await run(MIGRATIONS, sqlalchemy_url(empty_database_url))
                migrated.append(name)

    await asyncio.gather(start("first"), start("second"))

    assert migrated == ["first"] or migrated == ["second"], (
        f"expected exactly one process to migrate, got {migrated}"
    )

    conn = await asyncpg.connect(asyncpg_dsn(empty_database_url))
    try:
        assert await applied_heads(conn) == expected_heads(MIGRATIONS)
        assert await conn.fetchval("SELECT count(*) FROM alembic_version") == 1
    finally:
        await conn.close()


def test_this_modules_lock_key_is_still_its_own() -> None:
    """The key stopped being a constant in the file that takes the lock and became an
    argument this module supplies (`agent/runtime.py`). That is the whole risk of sharing
    `db.py`: a key silently changed — or silently shared with teams — would put two
    modules' migrations behind one lock, in databases neither can see, and the symptom
    would be a start-up that hangs with no failing query to find it by.
    """
    assert MIGRATION_LOCK_KEY == 8030
