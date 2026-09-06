"""Migrating at startup, and the lock that keeps two processes from doing it at once."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from urllib.parse import urlparse, urlunparse

import asyncpg
import pytest
from tc_runtime.migrate import run
from tc_runtime.schema_version import applied_heads, expected_heads

from market_data.db import (
    MIGRATION_LOCK_KEY,
    LockNotAcquired,
    advisory_lock,
    asyncpg_dsn,
    sqlalchemy_url,
)
from market_data.db import pool as make_pool
from market_data.runtime import MIGRATIONS


class FakeConnection:
    """Enough of a connection for the two statements `advisory_lock` runs. `taken` says the lock is
    held by somebody else, which is the case the wait exists for."""

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


def test_the_wait_outlasts_a_long_migration() -> None:
    """"Kres MUST być dłuższy niż najdłuższa migracja". Not a number this module can measure, so what
    is asserted is the ordering: this module's wait is the generous one."""
    from market_data.config import Settings

    assert Settings.model_fields["migration_lock_wait_seconds"].default >= 900


@pytest.fixture
async def empty_database_url(postgres_url: str) -> AsyncIterator[str]:
    """A database in the session's container that no migration has touched. `migrated_url` is session
    scoped, so a test needing an unmigrated one cannot share it — a fresh one costs a statement."""
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
        before = await conn.fetchval("SELECT version_num FROM alembic_version")

        await run(MIGRATIONS, sqlalchemy_url(migrated_url))

        assert await conn.fetchval("SELECT version_num FROM alembic_version") == before
        assert await conn.fetchval("SELECT count(*) FROM alembic_version") == 1
    finally:
        await conn.close()


@pytest.mark.db
async def test_only_one_of_two_processes_migrates(empty_database_url: str) -> None:
    """Two starts against one empty database, racing the way two App Service instances do. Each takes
    its own connection; the lock lives in the database, which is why it works across them."""
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

    assert len(migrated) == 1, f"expected exactly one process to migrate, got {migrated}"

    conn = await asyncpg.connect(asyncpg_dsn(empty_database_url))
    try:
        assert await applied_heads(conn) == expected_heads(MIGRATIONS)
        assert await conn.fetchval("SELECT count(*) FROM alembic_version") == 1
    finally:
        await conn.close()


@pytest.mark.db
async def test_nothing_is_collected_before_the_migration_finishes(
    migrated_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ordering inside the lifespan. Recorded rather than asserted on the clock: what matters is
    that `ingest.start()` cannot be reached before `migrate.run()` returned."""
    from market_data import app as app_module
    from market_data.ingest import Ingest
    from market_data.jobs.runner import JobRunner

    order: list[str] = []

    async def fake_migrate(database_url: str | None = None) -> None:
        del database_url
        order.append("migrate")

    async def fake_ingest_start(self: Ingest) -> None:
        del self
        order.append("ingest")

    async def noop(self: object) -> None:
        del self

    monkeypatch.setattr(app_module.migrate, "run", fake_migrate)
    monkeypatch.setattr(Ingest, "start", fake_ingest_start)
    monkeypatch.setattr(Ingest, "stop", noop)
    monkeypatch.setattr(JobRunner, "start", noop)
    monkeypatch.setattr(JobRunner, "stop", noop)
    monkeypatch.setenv("DATABASE_URL", migrated_url)
    monkeypatch.setenv("GATEWAY_API_KEY", "key")

    async with app_module.lifespan(app_module.app):
        pass

    assert order == ["migrate", "ingest"]
