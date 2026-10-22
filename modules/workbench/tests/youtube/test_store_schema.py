"""What the schema itself refuses. Only the rules a bug in the loop would otherwise get past: the ones that make a state
unaccountable, or a reading an opinion nobody stamped."""

from __future__ import annotations

import asyncpg
import pytest

pytestmark = pytest.mark.db


async def _film(db, video_id: str = "v1", **overrides) -> None:
    columns = {
        "video_id": video_id,
        "title": "a film",
        "published_at": "2026-09-27T10:00:00+00",
        "origins": ["manual"],
        "prompt_id": await db.fetchval("SELECT id FROM prompts WHERE seeded"),
        **overrides,
    }
    names = ", ".join(columns)
    marks = ", ".join(f"${i}" for i in range(1, len(columns) + 1))
    values = list(columns.values())
    if isinstance(values[2], str):
        from datetime import datetime

        values[2] = datetime.fromisoformat(values[2])
    await db.execute(f"INSERT INTO videos ({names}) VALUES ({marks})", *values)


async def test_a_film_is_one_row_however_it_arrived(db) -> None:
    await _film(db)

    with pytest.raises(asyncpg.UniqueViolationError):
        await _film(db, origins=["topic:7"])


async def test_a_skipped_film_must_say_why(db) -> None:
    with pytest.raises(asyncpg.CheckViolationError):
        await _film(db, state="skipped")

    await _film(db, video_id="v2", state="skipped", skip_reason="shorter than the floor")


async def test_a_reading_is_one_to_ten(db) -> None:
    await _film(db)

    with pytest.raises(asyncpg.CheckViolationError):
        await db.execute(
            "INSERT INTO readings (video_id, prompt_id, prompt_version, result, impact_score, model) "
            "VALUES ('v1', (SELECT id FROM prompts WHERE seeded), 1, '{}', 11, 'm')"
        )


async def test_removing_a_channel_leaves_its_films(db) -> None:
    """The watch list is why we looked, not what we keep: nothing references `channels`."""
    await db.execute(
        "INSERT INTO channels (channel_id, title, added_by, prompt_id) "
        "VALUES ('UC1', 'a channel', 'operator', (SELECT id FROM prompts WHERE seeded))"
    )
    await _film(db, channel_id="UC1")

    await db.execute("DELETE FROM channels WHERE channel_id = 'UC1'")

    assert await db.fetchval("SELECT count(*) FROM videos") == 1


async def test_the_same_phrase_in_another_case_is_the_same_topic(db) -> None:
    insert = (
        "INSERT INTO topics (phrase, interval_minutes, max_videos_per_run, added_by, prompt_id) "
        "VALUES ($1, 360, 3, 'agent', (SELECT id FROM prompts WHERE seeded))"
    )
    await db.execute(insert, "Gold outlook")

    with pytest.raises(asyncpg.UniqueViolationError):
        await db.execute(insert, "gold OUTLOOK")
