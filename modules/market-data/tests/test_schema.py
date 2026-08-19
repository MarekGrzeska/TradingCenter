"""What the migrations actually build.

Every test here runs against a database the real migrations were applied to, never
against a schema the fixture wrote itself — a hand-built table would prove that the test
knows what it wants and leave the migration, the thing a deployment runs, untried.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import asyncpg
import pytest
from asyncpg.exceptions import UniqueViolationError

from market_data.db import asyncpg_dsn, connect, sqlalchemy_url

pytestmark = pytest.mark.db

MODULE_ROOT = Path(__file__).resolve().parent.parent

PRIMARY_KEY_COLUMNS = """
    SELECT column_name
      FROM information_schema.key_column_usage
     WHERE table_name = $1 AND constraint_name = $2
     ORDER BY ordinal_position
"""


async def _table_names(conn: asyncpg.Connection) -> set[str]:
    rows = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    return {row["tablename"] for row in rows}


# --- the candle table (2.1) ---------------------------------------------------------


async def test_the_migrations_build_the_three_tables(db: asyncpg.Connection) -> None:
    assert {"candles", "tracked_pairs", "coverage_ranges"} <= await _table_names(db)


async def test_a_candle_is_identified_by_symbol_resolution_and_period_start(
    db: asyncpg.Connection,
) -> None:
    rows = await db.fetch(PRIMARY_KEY_COLUMNS, "candles", "candles_pkey")
    assert [row["column_name"] for row in rows] == ["symbol", "resolution", "period_start"]


# --- tracked pairs (2.2) ------------------------------------------------------------


async def test_a_tracked_pair_is_identified_by_symbol_and_resolution(
    db: asyncpg.Connection,
) -> None:
    rows = await db.fetch(PRIMARY_KEY_COLUMNS, "tracked_pairs", "tracked_pairs_pkey")
    assert [row["column_name"] for row in rows] == ["symbol", "resolution"]


# --- collection jobs (2.4) ----------------------------------------------------------


async def test_the_migrations_build_the_job_tables(db: asyncpg.Connection) -> None:
    assert {"collection_jobs", "collection_job_chunks"} <= await _table_names(db)


# --- the one constraint that is a rule, not a type ------------------------------------

# The enum and DEFAULT tests that stood here are gone: they asked whether PostgreSQL
# honours a CHECK, and every store test crosses these tables anyway. This one stays
# because a *partial* unique index is not a type — it is the rule that "how far back is
# there anything left to fetch" has one answer, and nothing else in the suite says so.


async def test_a_pair_has_at_most_one_end_of_provider_history(db: asyncpg.Connection) -> None:
    # Two of them would be two answers, and backfill would believe whichever row it read
    # first.
    moment = datetime(2026, 2, 16, 8, 0, tzinfo=UTC)
    await db.execute(
        "INSERT INTO coverage_ranges"
        " (symbol, resolution, range_start, range_end, history_ended, history_ends_at)"
        " VALUES ('US100', 'MINUTE', $1, $1, true, $1)",
        moment,
    )
    with pytest.raises(UniqueViolationError):
        await db.execute(
            "INSERT INTO coverage_ranges"
            " (symbol, resolution, range_start, range_end, history_ended, history_ends_at)"
            " VALUES ('US100', 'MINUTE', $1, $1, true, $1)",
            moment.replace(hour=9),
        )


# --- the migrations themselves ------------------------------------------------------


@pytest.fixture
async def scratch_database_url(postgres_url: str) -> AsyncIterator[str]:
    """An empty database of its own, so a migration test cannot disturb the shared one."""
    base, _, _ = postgres_url.rpartition("/")
    name = "migration_scratch"
    admin = await asyncpg.connect(asyncpg_dsn(postgres_url))
    try:
        await admin.execute(f'DROP DATABASE IF EXISTS "{name}"')
        await admin.execute(f'CREATE DATABASE "{name}"')
        yield f"{base}/{name}"
        await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    finally:
        await admin.close()


async def test_the_migrations_run_forwards_and_back(scratch_database_url: str) -> None:
    """Reversibility, checked once rather than discovered during an incident.

    This is the repository's first module with state it cannot afford to lose, so a
    downgrade that fails is not a theoretical inconvenience — it is the moment a bad
    deploy has to go forwards through a broken migration instead of backwards.
    """
    import asyncio

    from alembic import command
    from alembic.config import Config

    config = Config(str(MODULE_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(MODULE_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", sqlalchemy_url(scratch_database_url))

    # Alembic's environment calls asyncio.run, which refuses to nest inside the loop this
    # test is running on. A worker thread has no loop of its own, so it can.
    tables = {"candles", "tracked_pairs", "coverage_ranges", "collection_jobs", "collection_job_chunks"}

    await asyncio.to_thread(command.upgrade, config, "head")
    async with connect(scratch_database_url) as conn:
        assert tables <= await _table_names(conn)

    await asyncio.to_thread(command.downgrade, config, "base")
    async with connect(scratch_database_url) as conn:
        assert await _table_names(conn) & tables == set()
