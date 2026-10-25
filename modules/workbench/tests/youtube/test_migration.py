"""`0003` rewrites rows it did not write — every reading ever stored — so it is walked over a database that has some."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest
from alembic import command
from tc_runtime.db import asyncpg_dsn, sqlalchemy_url
from tc_runtime.migrate import alembic_config
from tc_runtime.schema_version import applied_heads, expected_heads

from youtube_data.runtime import MIGRATIONS

pytestmark = pytest.mark.db

OLD_READING = {
    "summary_pl": "Autor widzi złoto wyżej.",
    "key_points": ["banki kupują złoto"],
    "instruments": [{"name": "Gold", "epic": "XAUUSD", "sentiment": "bullish", "conviction": 4, "horizon": "swing"}],
    "predictions": [{"instrument": "Gold", "claim": "dochodzi do 3000", "level": 3000.0, "by": "2026-12-31"}],
    "topics": ["gold", "rates"],
    "impact_score": 6,
}


@pytest.fixture
async def old_database(postgres_url: str) -> AsyncIterator[str]:
    """A database of its own, migrated to `0002` and holding one of everything `0003` touches."""
    name = f"old_{uuid.uuid4().hex[:12]}"
    admin = await asyncpg.connect(asyncpg_dsn(postgres_url))
    try:
        await admin.execute(f'CREATE DATABASE "{name}"')
    finally:
        await admin.close()
    url = postgres_url.rsplit("/", 1)[0] + "/" + name
    config = alembic_config(MIGRATIONS, sqlalchemy_url(url))
    # In a thread because alembic's env.py drives its async engine with `asyncio.run`, which refuses to nest.
    await asyncio.to_thread(command.upgrade, config, "0002")
    conn = await asyncpg.connect(asyncpg_dsn(url))
    try:
        await conn.execute("INSERT INTO channels (channel_id, title, added_by) VALUES ('UC1', 'A channel', 'operator')")
        await conn.execute(
            "INSERT INTO topics (phrase, interval_minutes, max_videos_per_run, added_by) VALUES ('gold', 60, 3, 'agent')"
        )
        await conn.execute(
            "INSERT INTO videos (video_id, title, published_at, origins) VALUES ('v1', 'a film', now(), ARRAY['manual'])"
        )
        await conn.execute(
            "INSERT INTO readings (video_id, profile, result, impact_score, instruments, model) "
            "VALUES ('v1', 'market', $1::jsonb, 6, ARRAY['gold', 'xauusd'], 'm')",
            json.dumps(OLD_READING),
        )
    finally:
        await conn.close()
    yield url
    admin = await asyncpg.connect(asyncpg_dsn(postgres_url))
    try:
        await admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
    finally:
        await admin.close()


async def test_a_reading_in_the_old_shape_keeps_everything_it_said_and_everything_points_at_the_seeded_prompt(
    old_database: str,
) -> None:
    config = alembic_config(MIGRATIONS, sqlalchemy_url(old_database))

    await asyncio.to_thread(command.upgrade, config, "head")

    conn = await asyncpg.connect(asyncpg_dsn(old_database))
    try:
        seeded = await conn.fetchval("SELECT id FROM prompts WHERE seeded")
        for table in ("channels", "videos", "readings"):
            assert await conn.fetchval(f"SELECT DISTINCT prompt_id FROM {table}") == seeded, table
        row = await conn.fetchrow("SELECT result, impact_score, prompt_version FROM readings")
        result = json.loads(row["result"])
        assert (row["impact_score"], row["prompt_version"]) == (6, 1)
        assert result["summary_pl"] == OLD_READING["summary_pl"] and result["impact_score"] == 6
        assert set(result) == {"summary_pl", "text", "impact_score"}
        for said in ("banki kupują złoto", "Gold", "XAUUSD", "wzrost", "dochodzi do 3000", "3000.0", "2026-12-31", "rates"):
            assert said in result["text"], said
        assert await conn.fetchval("SELECT count(*) FROM prompt_versions WHERE prompt_id = $1", seeded) == 1
    finally:
        await conn.close()


async def test_the_migration_comes_back_down_and_up_again(old_database: str) -> None:
    """A downgrade nobody can reverse is a one-way door."""
    config = alembic_config(MIGRATIONS, sqlalchemy_url(old_database))
    await asyncio.to_thread(command.upgrade, config, "head")

    await asyncio.to_thread(command.downgrade, config, "0002")
    await asyncio.to_thread(command.upgrade, config, "head")

    conn = await asyncpg.connect(asyncpg_dsn(old_database))
    try:
        assert await applied_heads(conn) == expected_heads(MIGRATIONS)
    finally:
        await conn.close()


async def test_a_topic_outlives_the_migration_that_takes_its_prompt_and_the_candidate_tables_are_there(old_database: str) -> None:
    config = alembic_config(MIGRATIONS, sqlalchemy_url(old_database))

    await asyncio.to_thread(command.upgrade, config, "head")

    conn = await asyncpg.connect(asyncpg_dsn(old_database))
    try:
        assert await conn.fetchval("SELECT phrase FROM topics") == "gold"
        columns = {r["column_name"] for r in await conn.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'topics'"
        )}
        assert "prompt_id" not in columns
        assert await conn.fetchval("SELECT count(*) FROM candidates") == await conn.fetchval("SELECT count(*) FROM ignored_channels") == 0
    finally:
        await conn.close()


async def test_a_channel_from_before_the_filter_has_none_and_a_filtered_out_film_must_say_why(old_database: str) -> None:
    config = alembic_config(MIGRATIONS, sqlalchemy_url(old_database))

    await asyncio.to_thread(command.upgrade, config, "head")

    conn = await asyncpg.connect(asyncpg_dsn(old_database))
    try:
        assert await conn.fetchval("SELECT filter FROM channels WHERE channel_id = 'UC1'") is None
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute("UPDATE videos SET state = 'filtered_out' WHERE video_id = 'v1'")
    finally:
        await conn.close()


async def test_a_run_that_failed_or_was_skipped_must_say_why(old_database: str) -> None:
    config = alembic_config(MIGRATIONS, sqlalchemy_url(old_database))
    await asyncio.to_thread(command.upgrade, config, "head")

    conn = await asyncpg.connect(asyncpg_dsn(old_database))
    try:
        for outcome in ("failed", "skipped"):
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute(
                    "INSERT INTO topic_runs (topic_id, phrase, ran_at, outcome) VALUES (1, 'gold', now(), $1)", outcome
                )
        await conn.execute("INSERT INTO topic_runs (topic_id, phrase, ran_at, outcome) VALUES (1, 'gold', now(), 'nothing_new')")
    finally:
        await conn.close()


async def test_a_language_written_as_a_name_becomes_its_code_and_the_hold_from_its_400s_is_lifted(old_database: str) -> None:
    config = alembic_config(MIGRATIONS, sqlalchemy_url(old_database))
    await asyncio.to_thread(command.upgrade, config, "0008")
    conn = await asyncpg.connect(asyncpg_dsn(old_database))
    try:
        await conn.execute(
            "INSERT INTO topics (phrase, language, interval_minutes, max_videos_per_run, added_by, retry_at) VALUES "
            "('rynki', 'Polish', 360, 5, 'agent', now()), ('markets', 'English', 360, 5, 'agent', now()), "
            "('markets', 'en', 360, 5, 'operator', NULL)"
        )
        await asyncio.to_thread(command.upgrade, config, "head")

        rows = await conn.fetch("SELECT phrase, language, retry_at IS NULL AS free FROM topics WHERE phrase <> 'gold' ORDER BY phrase, language")
        # The second 'markets' would collide with the one already under `en`, so it is left for the operator to remove.
        assert [tuple(r) for r in rows] == [("markets", "English", False), ("markets", "en", True), ("rynki", "pl", True)]
    finally:
        await conn.close()
