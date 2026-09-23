"""Migrating at startup, and the lock that keeps two processes from doing it at once."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse, urlunparse

import asyncpg
import pytest
from tc_runtime.db import advisory_lock, asyncpg_dsn, sqlalchemy_url
from tc_runtime.db import pool as make_pool
from tc_runtime.migrate import run
from tc_runtime.schema_version import SchemaMismatch, applied_heads, expected_heads, verify

from polymarket_data.runtime import MIGRATION_LOCK_KEY, MIGRATIONS


@pytest.fixture
async def empty_database_url(postgres_url: str) -> AsyncIterator[str]:
    """A database in the session's container that no migration has touched. `migrated_url` is session
    scoped, so a test needing an unmigrated one cannot share it or rely on running first."""
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
async def test_a_database_at_no_revision_is_refused_before_it_serves(
    empty_database_url: str,
) -> None:
    """The check that runs after migrating, for the case a migration cannot fix: an upgrade
    that reported success without arriving."""
    conn = await asyncpg.connect(asyncpg_dsn(empty_database_url))
    try:
        with pytest.raises(SchemaMismatch, match="never migrated"):
            await verify(conn, MIGRATIONS)
    finally:
        await conn.close()


@pytest.mark.db
async def test_only_one_of_two_processes_migrates(empty_database_url: str) -> None:
    """Two starts against one empty database, racing the way two App Service instances do. Each takes its
    own connection; the lock lives in the database, which is why it works across them."""
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

    assert migrated in (["first"], ["second"]), (
        f"expected exactly one process to migrate, got {migrated}"
    )

    conn = await asyncpg.connect(asyncpg_dsn(empty_database_url))
    try:
        assert await applied_heads(conn) == expected_heads(MIGRATIONS)
        assert await conn.fetchval("SELECT count(*) FROM alembic_version") == 1
    finally:
        await conn.close()


@pytest.mark.db
async def test_the_chain_comes_back_down_and_up_again(empty_database_url: str) -> None:
    """A downgrade nobody can reverse is a one-way door, and the drop order in `0001` is the
    kind of thing that only fails when it is run."""
    from alembic import command
    from tc_runtime.migrate import alembic_config

    config = alembic_config(MIGRATIONS, sqlalchemy_url(empty_database_url))
    await asyncio.to_thread(command.upgrade, config, "head")
    await asyncio.to_thread(command.downgrade, config, "base")

    conn = await asyncpg.connect(asyncpg_dsn(empty_database_url))
    try:
        assert await conn.fetchval(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_name IN ('price_samples', 'outcomes', 'markets', "
            "'tracked_events', 'observation_groups', 'collected_ranges')"
        ) == 0
    finally:
        await conn.close()

    await asyncio.to_thread(command.upgrade, config, "head")
    conn = await asyncpg.connect(asyncpg_dsn(empty_database_url))
    try:
        assert await applied_heads(conn) == expected_heads(MIGRATIONS)
    finally:
        await conn.close()


@pytest.mark.db
async def test_0003_takes_the_stopped_observations_and_leaves_the_rest(
    empty_database_url: str,
) -> None:
    """The one migration in this module that deletes collected history. It runs once against whatever a
    production database holds, with no second chance, so it is walked here rather than reasoned about."""
    from alembic import command
    from tc_runtime.migrate import alembic_config

    url = sqlalchemy_url(empty_database_url)
    await asyncio.to_thread(command.upgrade, alembic_config(MIGRATIONS, url), "0002")

    conn = await asyncpg.connect(asyncpg_dsn(empty_database_url))
    try:
        for provider_event_id, stopped in (("gone", True), ("kept", False)):
            event_id = await conn.fetchval(
                """
                INSERT INTO tracked_events (provider_event_id, slug, title, tracking_ended_at)
                VALUES ($1, $1, $1, CASE WHEN $2 THEN now() ELSE NULL END)
                RETURNING id
                """,
                provider_event_id,
                stopped,
            )
            market_id = await conn.fetchval(
                """
                INSERT INTO markets (event_id, provider_market_id, condition_id, question)
                VALUES ($1, $2, $2, 'q') RETURNING id
                """,
                event_id,
                f"m-{provider_event_id}",
            )
            outcome_id = await conn.fetchval(
                """
                INSERT INTO outcomes (market_id, position, name, token_id)
                VALUES ($1, 0, 'Yes', $2) RETURNING id
                """,
                market_id,
                f"t-{provider_event_id}",
            )
            await conn.execute(
                """
                INSERT INTO price_samples (outcome_id, observed_at, midpoint, source)
                VALUES ($1, now(), 0.5, 'gamma')
                """,
                outcome_id,
            )

        await asyncio.to_thread(command.upgrade, alembic_config(MIGRATIONS, url), "head")

        assert [
            row["provider_event_id"]
            for row in await conn.fetch("SELECT provider_event_id FROM tracked_events")
        ] == ["kept"]
        # The cascade is what makes this one act rather than four, so the sample of the
        # stopped one has to be gone too — and the kept one's has to still be there.
        assert await conn.fetchval("SELECT count(*) FROM price_samples") == 1
        assert await conn.fetchval(
            """
            SELECT count(*) FROM information_schema.columns
            WHERE table_name = 'tracked_events' AND column_name = 'tracking_ended_at'
            """
        ) == 0
    finally:
        await conn.close()


@pytest.mark.db
async def test_duplicate_spellings_are_merged_into_the_oldest_before_the_index(
    empty_database_url: str,
) -> None:
    """`0005` rewrites rows it did not write — production held groups models had made twice — so the merge
    is walked rather than trusted: the events move to the oldest spelling, and nothing is lost."""
    from alembic import command
    from tc_runtime.migrate import alembic_config

    config = alembic_config(MIGRATIONS, sqlalchemy_url(empty_database_url))
    await asyncio.to_thread(command.upgrade, config, "0004")

    conn = await asyncpg.connect(asyncpg_dsn(empty_database_url))
    try:
        oldest = await conn.fetchval("INSERT INTO observation_groups (name) VALUES ('Crypto') RETURNING id")
        twin = await conn.fetchval("INSERT INTO observation_groups (name) VALUES (E' crypto\t') RETURNING id")
        await conn.execute(
            "INSERT INTO tracked_events (provider_event_id, slug, title, group_id) "
            "VALUES ('e-1', 'e-1', 'one', $1), ('e-2', 'e-2', 'two', $2)",
            oldest,
            twin,
        )

        await asyncio.to_thread(command.upgrade, config, "head")

        assert await conn.fetch("SELECT id, name FROM observation_groups") == [(oldest, "Crypto")]
        assert await conn.fetchval("SELECT count(*) FROM tracked_events WHERE group_id = $1", oldest) == 2
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute("INSERT INTO observation_groups (name) VALUES ('CRYPTO')")
    finally:
        await conn.close()


@pytest.mark.db
async def test_0007_merges_the_ranges_that_touch_and_keeps_the_gaps(empty_database_url: str) -> None:
    """Rewrites every range production ever wrote, once, so walked rather than trusted: a gap it closed
    would read as collected for ever, and backfill would never go back to it."""
    from alembic import command
    from tc_runtime.migrate import alembic_config

    config = alembic_config(MIGRATIONS, sqlalchemy_url(empty_database_url))
    await asyncio.to_thread(command.upgrade, config, "0006")

    conn = await asyncpg.connect(asyncpg_dsn(empty_database_url))
    try:
        event_id = await conn.fetchval(
            "INSERT INTO tracked_events (provider_event_id, slug, title) VALUES ('e', 'e', 'e') RETURNING id"
        )
        market_id = await conn.fetchval(
            "INSERT INTO markets (event_id, provider_market_id, condition_id, question) "
            "VALUES ($1, 'm', 'm', 'q') RETURNING id",
            event_id,
        )
        first, second = [
            await conn.fetchval(
                "INSERT INTO outcomes (market_id, position, name, token_id) "
                "VALUES ($1, $2, $3, $3) RETURNING id",
                market_id,
                position,
                name,
            )
            for position, name in ((0, "Yes"), (1, "No"))
        ]
        minute = timedelta(minutes=1)
        t0 = datetime(2026, 9, 1, tzinfo=UTC)
        ranges = [
            (first, t0, t0 + minute),  # touches the next at its end
            (first, t0 + minute, t0 + 2 * minute),
            (first, t0 + timedelta(seconds=90), t0 + 3 * minute),  # overlaps
            (first, t0 + 10 * minute, t0 + 11 * minute),  # after a gap
            (second, t0, t0 + minute),  # another outcome's, touching nothing of the first's
        ]
        await conn.executemany(
            "INSERT INTO collected_ranges (outcome_id, starts_at, ends_at) VALUES ($1, $2, $3)", ranges
        )

        await asyncio.to_thread(command.upgrade, config, "head")

        rows = await conn.fetch(
            "SELECT outcome_id, starts_at, ends_at FROM collected_ranges ORDER BY outcome_id, starts_at"
        )
        assert [tuple(row) for row in rows] == [
            (first, t0, t0 + 3 * minute),
            (first, t0 + 10 * minute, t0 + 11 * minute),
            (second, t0, t0 + minute),
        ]
    finally:
        await conn.close()
