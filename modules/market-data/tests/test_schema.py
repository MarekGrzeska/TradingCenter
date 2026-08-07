"""What the migrations actually build.

Every test here runs against a database the real migrations were applied to, never
against a schema the fixture wrote itself — a hand-built table would prove that the test
knows what it wants and leave the migration, the thing a deployment runs, untried.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import asyncpg
import pytest
from asyncpg.exceptions import CheckViolationError, UniqueViolationError

from market_data.db import asyncpg_dsn, connect, sqlalchemy_url

pytestmark = pytest.mark.db

MODULE_ROOT = Path(__file__).resolve().parent.parent

MOMENT = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)

PRIMARY_KEY_COLUMNS = """
    SELECT column_name
      FROM information_schema.key_column_usage
     WHERE table_name = $1 AND constraint_name = $2
     ORDER BY ordinal_position
"""


async def _table_names(conn: asyncpg.Connection) -> set[str]:
    rows = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    return {row["tablename"] for row in rows}


async def _insert_candle(conn: asyncpg.Connection, **overrides) -> None:
    values = {
        "symbol": "US100",
        "resolution": "MINUTE",
        "period_start": MOMENT,
        "source": "history",
        **overrides,
    }
    columns = ", ".join(values)
    placeholders = ", ".join(f"${n}" for n in range(1, len(values) + 1))
    await conn.execute(
        f"INSERT INTO candles ({columns}) VALUES ({placeholders})", *values.values()
    )


# --- the candle table (2.1) ---------------------------------------------------------


async def test_the_migrations_build_the_three_tables(db: asyncpg.Connection) -> None:
    assert {"candles", "tracked_pairs", "coverage_ranges"} <= await _table_names(db)


async def test_a_candle_is_identified_by_symbol_resolution_and_period_start(
    db: asyncpg.Connection,
) -> None:
    rows = await db.fetch(PRIMARY_KEY_COLUMNS, "candles", "candles_pkey")
    assert [row["column_name"] for row in rows] == ["symbol", "resolution", "period_start"]


async def test_a_second_row_for_the_same_triple_is_refused(db: asyncpg.Connection) -> None:
    # The overwrite is the store's business; the table's business is making a duplicate
    # impossible even for something that bypasses the store.
    await _insert_candle(db)
    with pytest.raises(UniqueViolationError):
        await _insert_candle(db)


async def test_the_price_side_is_written_and_defaults_to_bid(db: asyncpg.Connection) -> None:
    # Recorded next to the data rather than assumed, so that adding the ask side one day
    # cannot quietly mix two series into one.
    await _insert_candle(db)
    assert await db.fetchval("SELECT price_side FROM candles") == "bid"


async def test_a_price_side_the_module_does_not_know_is_refused(db: asyncpg.Connection) -> None:
    with pytest.raises(CheckViolationError):
        await _insert_candle(db, price_side="mid")


async def test_a_resolution_outside_the_gateway_vocabulary_is_refused(
    db: asyncpg.Connection,
) -> None:
    # The vocabulary travels over the gateway's contract verbatim; a spelling it never
    # publishes is a typo that would otherwise sit in the archive as its own series.
    with pytest.raises(CheckViolationError):
        await _insert_candle(db, resolution="MINUTE_2")


async def test_a_source_the_module_does_not_know_is_refused(db: asyncpg.Connection) -> None:
    with pytest.raises(CheckViolationError):
        await _insert_candle(db, source="guess")


async def test_a_candle_edge_may_be_missing(db: asyncpg.Connection) -> None:
    # The provider occasionally omits one, and a candle short an edge is still better
    # evidence than a gap.
    await _insert_candle(db, open=1.0, high=2.0, low=0.5)
    assert await db.fetchval("SELECT close FROM candles") is None


# --- tracked pairs (2.2) ------------------------------------------------------------


async def test_a_tracked_pair_is_identified_by_symbol_and_resolution(
    db: asyncpg.Connection,
) -> None:
    rows = await db.fetch(PRIMARY_KEY_COLUMNS, "tracked_pairs", "tracked_pairs_pkey")
    assert [row["column_name"] for row in rows] == ["symbol", "resolution"]


async def test_a_new_pair_is_tracked_and_stamped_with_when_it_was_added(
    db: asyncpg.Connection,
) -> None:
    await db.execute("INSERT INTO tracked_pairs (symbol, resolution) VALUES ('US100', 'MINUTE')")
    row = await db.fetchrow("SELECT state, added_at, untracked_at FROM tracked_pairs")
    assert row["state"] == "tracked"
    assert row["untracked_at"] is None
    # Stamped by the database, so the moment is recorded whether or not a caller
    # remembered to supply one. Compared loosely: the container's clock is not the host's,
    # and a test that fails on a minute of drift proves nothing about the schema.
    assert row["added_at"].tzinfo is not None
    assert abs(row["added_at"] - datetime.now(UTC)) < timedelta(days=1)


async def test_untracking_records_when_collection_stopped(db: asyncpg.Connection) -> None:
    # The row survives untracking so that tracking the pair again knows which gap to
    # close, and so that the candles already collected are never in question.
    await db.execute("INSERT INTO tracked_pairs (symbol, resolution) VALUES ('US100', 'MINUTE')")
    await db.execute(
        "UPDATE tracked_pairs SET state = 'untracked', untracked_at = $1", MOMENT
    )
    row = await db.fetchrow("SELECT state, untracked_at FROM tracked_pairs")
    assert (row["state"], row["untracked_at"]) == ("untracked", MOMENT)


async def test_an_untracked_pair_without_a_stopping_point_is_refused(
    db: asyncpg.Connection,
) -> None:
    await db.execute("INSERT INTO tracked_pairs (symbol, resolution) VALUES ('US100', 'MINUTE')")
    with pytest.raises(CheckViolationError):
        await db.execute("UPDATE tracked_pairs SET state = 'untracked'")


async def test_a_tracked_pair_carrying_a_stopping_point_is_refused(
    db: asyncpg.Connection,
) -> None:
    with pytest.raises(CheckViolationError):
        await db.execute(
            "INSERT INTO tracked_pairs (symbol, resolution, untracked_at)"
            " VALUES ('US100', 'MINUTE', $1)",
            MOMENT,
        )


# --- coverage ranges (2.3) ----------------------------------------------------------


async def test_coverage_does_not_claim_a_provider_boundary_by_default(
    db: asyncpg.Connection,
) -> None:
    await db.execute(
        "INSERT INTO coverage_ranges (symbol, resolution, range_start, range_end)"
        " VALUES ('US100', 'MINUTE', $1, $2)",
        MOMENT,
        MOMENT,
    )
    assert await db.fetchval("SELECT history_ended FROM coverage_ranges") is False


async def test_an_inverted_range_is_refused(db: asyncpg.Connection) -> None:
    with pytest.raises(CheckViolationError):
        await db.execute(
            "INSERT INTO coverage_ranges (symbol, resolution, range_start, range_end)"
            " VALUES ('US100', 'MINUTE', $1, $2)",
            MOMENT,
            MOMENT.replace(hour=11),
        )


async def test_a_pair_has_at_most_one_end_of_provider_history(db: asyncpg.Connection) -> None:
    # Two of them would be two answers to "how far back is there anything left to
    # fetch", and backfill would believe whichever row it read first.
    await db.execute(
        "INSERT INTO coverage_ranges (symbol, resolution, range_start, range_end, history_ended)"
        " VALUES ('US100', 'MINUTE', $1, $1, true)",
        MOMENT,
    )
    with pytest.raises(UniqueViolationError):
        await db.execute(
            "INSERT INTO coverage_ranges"
            " (symbol, resolution, range_start, range_end, history_ended)"
            " VALUES ('US100', 'MINUTE', $1, $1, true)",
            MOMENT.replace(hour=9),
        )


async def test_ranges_without_a_provider_boundary_may_be_many(db: asyncpg.Connection) -> None:
    for hour in (9, 10, 11):
        await db.execute(
            "INSERT INTO coverage_ranges (symbol, resolution, range_start, range_end)"
            " VALUES ('US100', 'MINUTE', $1, $1)",
            MOMENT.replace(hour=hour),
        )
    assert await db.fetchval("SELECT count(*) FROM coverage_ranges") == 3


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
    await asyncio.to_thread(command.upgrade, config, "head")
    async with connect(scratch_database_url) as conn:
        assert {"candles", "tracked_pairs", "coverage_ranges"} <= await _table_names(conn)

    await asyncio.to_thread(command.downgrade, config, "base")
    async with connect(scratch_database_url) as conn:
        assert await _table_names(conn) & {"candles", "tracked_pairs", "coverage_ranges"} == set()
