"""Migrating at startup, and the lock that keeps two processes from doing it at once."""

from __future__ import annotations

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


@pytest.mark.db
async def test_an_empty_database_stays_at_the_empty_head(postgres_url: str) -> None:
    """There are zero migrations yet, so this proves the machinery — `MIGRATIONS`
    resolving, `alembic_config()`, the worker-thread run — works end to end against a
    real database, not that any table gets created."""
    conn = await asyncpg.connect(asyncpg_dsn(postgres_url))
    try:
        assert await applied_heads(conn) == set()

        await run(sqlalchemy_url(postgres_url))

        assert await applied_heads(conn) == expected_heads() == set()
    finally:
        await conn.close()


@pytest.mark.db
async def test_running_twice_does_not_raise(postgres_url: str) -> None:
    await run(sqlalchemy_url(postgres_url))
    await run(sqlalchemy_url(postgres_url))


@pytest.mark.db
async def test_the_lock_is_taken_and_released_around_a_real_migration(postgres_url: str) -> None:
    """`run()` end to end, through a connection taken from the pool the way `app.py`'s
    lifespan takes one — proving the lock and the migration compose, not just that each
    works alone (which the tests above and in `test_db.py` already cover with fakes)."""
    async with (
        make_pool(postgres_url, min_size=1, max_size=1) as pool,
        pool.acquire() as conn,
        advisory_lock(conn, MIGRATION_LOCK_KEY, wait=5.0),
    ):
        await run(sqlalchemy_url(postgres_url))
        assert await applied_heads(conn) == expected_heads()
