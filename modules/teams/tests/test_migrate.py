"""Migrating at startup, and the lock that keeps two processes from doing it at once."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from urllib.parse import urlparse, urlunparse

import asyncpg
import pytest
from tc_runtime.db import advisory_lock, asyncpg_dsn, sqlalchemy_url
from tc_runtime.db import pool as make_pool
from tc_runtime.migrate import run
from tc_runtime.schema_version import applied_heads, expected_heads

from teams.runtime import MIGRATION_LOCK_KEY, MIGRATIONS


@pytest.fixture
async def empty_database_url(postgres_url: str) -> AsyncIterator[str]:
    """A database in the session's container that no migration has touched.

    `migrated_url` is session scoped and runs the migrations once for everything that
    asks for it, so a test needing an *unmigrated* database cannot share it — and
    cannot rely on running before it either. A fresh logical database costs one
    statement.
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

        heads = await applied_heads(conn)
        assert heads == expected_heads(MIGRATIONS)
        assert heads  # no longer the empty-head state group 1 shipped
    finally:
        await conn.close()


@pytest.mark.db
async def test_a_database_already_at_head_is_left_alone(migrated_url: str) -> None:
    conn = await asyncpg.connect(asyncpg_dsn(migrated_url))
    try:
        before = await conn.fetchval("SELECT count(*) FROM teams")

        await run(MIGRATIONS, sqlalchemy_url(migrated_url))

        # None of these migrations seed data, so a second run leaving the row count
        # alone is the whole of what "left alone" can mean here.
        assert await conn.fetchval("SELECT count(*) FROM teams") == before
    finally:
        await conn.close()


@pytest.mark.db
async def test_the_lock_is_taken_and_released_around_a_real_migration(empty_database_url: str) -> None:
    """`run()` end to end, through a connection taken from the pool the way `app.py`'s
    lifespan takes one — proving the lock and the migration compose, not just that each
    works alone (which the tests above and in `test_db.py` already cover with fakes)."""
    async with (
        make_pool(empty_database_url, min_size=1, max_size=1) as pool,
        pool.acquire() as conn,
        advisory_lock(conn, MIGRATION_LOCK_KEY, wait=5.0),
    ):
        await run(MIGRATIONS, sqlalchemy_url(empty_database_url))
        assert await applied_heads(conn) == expected_heads(MIGRATIONS)


def test_this_modules_lock_key_is_still_its_own() -> None:
    """The key stopped being a constant in the file that takes the lock and became an
    argument this module supplies (`teams/runtime.py`). Agent takes 8030 from the same
    helper; if these two ever met, two modules' migrations would queue behind one lock in
    databases neither can see, and the symptom would be a start-up that hangs with no
    failing query to find it by."""
    assert MIGRATION_LOCK_KEY == 8050
