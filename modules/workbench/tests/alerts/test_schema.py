"""The schema as the migration builds it. Only what the application relies on and a constraint can refuse."""

from __future__ import annotations

import asyncpg
import pytest

pytestmark = pytest.mark.db

EVENT_TYPE = "INSERT INTO event_types (name, description, schema) VALUES ('t', 'd', '{}')"
RULE_COLUMNS = "name, kind, destination, template, cooldown_seconds, mode, created_by"


async def test_the_migration_creates_every_table(db) -> None:
    found = {
        row["tablename"]
        for row in await db.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    }

    assert {"event_types", "events", "rules", "rule_checks", "fires", "draft_usage", "migrations_done"} <= found


async def test_a_rule_with_both_sources_is_refused(db) -> None:
    await db.execute(EVENT_TYPE)

    with pytest.raises(asyncpg.CheckViolationError):
        await db.execute(
            f"INSERT INTO rules ({RULE_COLUMNS}, tool_name, field_path, comparison, threshold, "
            "poll_interval_seconds, event_type) "
            "VALUES ('both', 'condition', 'phone', '{value}', 900, 'repeat', 'operator', "
            "'get_last_price', 'close', 'gt', 1.10, 60, 't')"
        )


async def test_a_second_publication_of_the_same_event_is_refused(db) -> None:
    await db.execute(EVENT_TYPE)
    insert = "INSERT INTO events (type, source_key, attributes, text) VALUES ('t', 'film-1', '{}', 'x')"
    await db.execute(insert)

    with pytest.raises(asyncpg.UniqueViolationError):
        await db.execute(insert)


async def test_deleting_an_event_leaves_the_fire_it_caused(db) -> None:
    await db.execute(EVENT_TYPE)
    event_id = await db.fetchval(
        "INSERT INTO events (type, source_key, attributes, text) VALUES ('t', 'film-1', '{}', 'x') RETURNING id"
    )
    rule_id = await db.fetchval(
        f"INSERT INTO rules ({RULE_COLUMNS}, event_type) "
        "VALUES ('films', 'event', 'phone', '{text}', 0, 'repeat', 'operator', 't') RETURNING id"
    )
    await db.execute(
        "INSERT INTO fires (rule_id, event_id, state, text) VALUES ($1, $2, 'delivered', 'x')", rule_id, event_id
    )

    await db.execute("DELETE FROM events WHERE id = $1", event_id)

    assert await db.fetchval("SELECT count(*) FROM fires WHERE rule_id = $1", rule_id) == 1
