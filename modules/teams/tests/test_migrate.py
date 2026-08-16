"""Migrating at startup, and the lock that keeps two processes from doing it at once."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from urllib.parse import urlparse, urlunparse

import asyncpg
import pytest

from teams.db import (
    MIGRATION_LOCK_KEY,
    LockNotAcquired,
    advisory_lock,
    asyncpg_dsn,
    sqlalchemy_url,
)
from teams.db import pool as make_pool
from teams.migrate import run
from teams.schema_version import applied_heads, expected_heads


class FakeConnection:
    """Enough of a connection for the two statements `advisory_lock` runs.

    `taken` says the lock is held by somebody else — every `pg_try_advisory_lock` answers
    false, which is the case the wait exists for.
    """

    def __init__(self, *, taken: bool = False) -> None:
        self._taken = taken
        self.unlocked = False

    async def fetchval(self, query: str, key: int) -> bool:
        del key
        if "pg_try_advisory_lock" in query:
            return not self._taken
        self.unlocked = True
        return True


async def test_the_lock_is_released_when_the_body_raises() -> None:
    # The failure that matters: a migration that blew up must not leave the next process
    # waiting on a lock nobody is using.
    conn = FakeConnection()

    with pytest.raises(RuntimeError, match="migration blew up"):
        async with advisory_lock(conn, MIGRATION_LOCK_KEY, wait=1.0):  # type: ignore[arg-type]
            raise RuntimeError("migration blew up")

    assert conn.unlocked


async def test_a_lock_that_never_frees_up_refuses_rather_than_waits_forever() -> None:
    conn = FakeConnection(taken=True)

    with pytest.raises(LockNotAcquired) as err:
        async with advisory_lock(conn, MIGRATION_LOCK_KEY, wait=0.05, poll=0.01):  # type: ignore[arg-type]
            pass  # pragma: no cover - the lock is never granted

    assert str(MIGRATION_LOCK_KEY) in str(err.value)
    # Refusing means never entering the body, so there was nothing to unlock.
    assert not conn.unlocked


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

        await run(sqlalchemy_url(empty_database_url))

        heads = await applied_heads(conn)
        assert heads == expected_heads()
        assert heads  # no longer the empty-head state group 1 shipped
    finally:
        await conn.close()


@pytest.mark.db
async def test_a_database_already_at_head_is_left_alone(migrated_url: str) -> None:
    conn = await asyncpg.connect(asyncpg_dsn(migrated_url))
    try:
        before = await conn.fetchval("SELECT count(*) FROM teams")

        await run(sqlalchemy_url(migrated_url))

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
        await run(sqlalchemy_url(empty_database_url))
        assert await applied_heads(conn) == expected_heads()
