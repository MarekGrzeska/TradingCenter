"""Every statement this package makes, in one place. Rules and event types here; the events, looks and fires arrive with
the groups that write them."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any

import asyncpg
from tc_runtime.db import Conn, fetch_one

from .contract import ConditionSource, EventSource, RuleIn
from .validation import effective_cooldown, effective_template

RULE_COLUMNS = """
    id, name, kind, destination, template, cooldown_seconds, mode, max_per_hour,
    tool_name, arguments, field_path, comparison, threshold, poll_interval_seconds,
    event_type, filter, enabled, disabled_reason, defect,
    next_check_at, last_result, last_known_result, last_checked_at, last_fired_at, throttle_notified_at,
    created_by, created_at, updated_at
"""


def json_of(value: Any) -> Any:
    """A `jsonb` column as the value it holds. asyncpg hands it back as text unless a codec says otherwise."""
    return json.loads(value) if isinstance(value, str) else value


def _source_columns(rule: RuleIn) -> tuple[Any, ...]:
    """The eight source columns in table order; those of the other kind stay null, which the table's check requires."""
    source = rule.source
    if isinstance(source, ConditionSource):
        return (
            "condition",
            source.tool_name,
            json.dumps(source.arguments),
            source.field_path,
            source.comparison,
            Decimal(source.threshold),
            source.poll_interval_seconds,
            None,
            None,
        )
    assert isinstance(source, EventSource)
    return (
        "event",
        None,
        None,
        None,
        None,
        None,
        None,
        source.event_type,
        json.dumps([term.model_dump() for term in source.filter]),
    )


async def insert_rule(conn: Conn, rule: RuleIn, *, created_by: str, now: datetime) -> asyncpg.Record:
    kind, tool, arguments, field, comparison, threshold, interval, event_type, filter_ = _source_columns(rule)
    return await fetch_one(
        conn,
        f"""
        INSERT INTO rules (
            name, kind, destination, template, cooldown_seconds, mode, max_per_hour, enabled,
            tool_name, arguments, field_path, comparison, threshold, poll_interval_seconds,
            event_type, filter, next_check_at, created_by
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11, $12, $13, $14, $15, $16::jsonb, $17, $18)
        RETURNING {RULE_COLUMNS}
        """,
        rule.name,
        kind,
        rule.destination,
        effective_template(rule),
        effective_cooldown(rule),
        rule.mode,
        rule.max_per_hour,
        rule.enabled,
        tool,
        arguments,
        field,
        comparison,
        threshold,
        interval,
        event_type,
        filter_,
        now if kind == "condition" and rule.enabled else None,
        created_by,
    )


async def replace_rule(conn: Conn, rule_id: int, rule: RuleIn, *, now: datetime) -> asyncpg.Record | None:
    """The rule as written again. What it had learned about its value is forgotten with the value it was learned from:
    a threshold that moved makes the last result a statement about a different question."""
    kind, tool, arguments, field, comparison, threshold, interval, event_type, filter_ = _source_columns(rule)
    return await conn.fetchrow(
        f"""
        UPDATE rules SET
            name = $2, kind = $3, destination = $4, template = $5, cooldown_seconds = $6, mode = $7,
            max_per_hour = $8, enabled = $9, disabled_reason = NULL,
            tool_name = $10, arguments = $11::jsonb, field_path = $12, comparison = $13, threshold = $14,
            poll_interval_seconds = $15, event_type = $16, filter = $17::jsonb,
            defect = NULL, next_check_at = $18, last_result = NULL, last_known_result = NULL,
            throttle_notified_at = NULL, updated_at = now()
         WHERE id = $1
        RETURNING {RULE_COLUMNS}
        """,
        rule_id,
        rule.name,
        kind,
        rule.destination,
        effective_template(rule),
        effective_cooldown(rule),
        rule.mode,
        rule.max_per_hour,
        rule.enabled,
        tool,
        arguments,
        field,
        comparison,
        threshold,
        interval,
        event_type,
        filter_,
        now if kind == "condition" and rule.enabled else None,
    )


async def set_enabled(
    conn: Conn, rule_id: int, enabled: bool, *, now: datetime
) -> asyncpg.Record | None:
    """Switched on, a value rule is looked at again at once and starts from no memory of its last result; switched off,
    it says by whom, so a rule that stopped on its own and one that was stopped read differently."""
    return await conn.fetchrow(
        f"""
        UPDATE rules SET
            enabled = $2,
            disabled_reason = CASE WHEN $2 THEN NULL ELSE 'switched off by the operator' END,
            next_check_at = CASE WHEN $2 AND kind = 'condition' THEN $3::timestamptz ELSE NULL END,
            last_result = CASE WHEN $2 THEN NULL ELSE last_result END,
            last_known_result = CASE WHEN $2 THEN NULL ELSE last_known_result END,
            updated_at = now()
         WHERE id = $1
        RETURNING {RULE_COLUMNS}
        """,
        rule_id,
        enabled,
        now,
    )


async def get_rule(conn: Conn, rule_id: int) -> asyncpg.Record | None:
    return await conn.fetchrow(f"SELECT {RULE_COLUMNS} FROM rules WHERE id = $1", rule_id)


async def list_rules(conn: Conn) -> list[asyncpg.Record]:
    return list(await conn.fetch(f"SELECT {RULE_COLUMNS} FROM rules ORDER BY id"))


async def delete_rule(conn: Conn, rule_id: int) -> bool:
    result = await conn.execute("DELETE FROM rules WHERE id = $1", rule_id)
    return result.endswith(" 1")


async def set_defect(conn: Conn, rule_id: int, defect: str | None) -> None:
    await conn.execute("UPDATE rules SET defect = $2 WHERE id = $1", rule_id, defect)


async def rules_of_event_type(conn: Conn, event_type: str) -> list[asyncpg.Record]:
    return list(
        await conn.fetch(f"SELECT {RULE_COLUMNS} FROM rules WHERE kind = 'event' AND event_type = $1", event_type)
    )


async def upsert_event_type(
    conn: Conn, name: str, *, description: str, schema: dict[str, Any], announced_by: str | None
) -> None:
    """An announcement, again or for the first time. The newer schema replaces the older: a producer that changed what it
    carries is the authority on what it carries."""
    await conn.execute(
        """
        INSERT INTO event_types (name, description, schema, announced_by)
        VALUES ($1, $2, $3::jsonb, $4)
        ON CONFLICT (name) DO UPDATE SET
            description = EXCLUDED.description,
            schema = EXCLUDED.schema,
            announced_by = COALESCE(EXCLUDED.announced_by, event_types.announced_by),
            last_announced_at = now()
        """,
        name,
        description,
        json.dumps(schema),
        announced_by,
    )


async def list_event_types(conn: Conn) -> list[asyncpg.Record]:
    return list(
        await conn.fetch(
            "SELECT name, description, schema, announced_by, last_announced_at FROM event_types ORDER BY name"
        )
    )


# --- looking at values ----------------------------------------------------------------------------------------------


async def claim_due(conn: Conn, *, limit: int, now: datetime) -> list[asyncpg.Record]:
    """The value rules whose turn has come, each moved on by its own interval in the same statement. Claiming is what
    stops two instances — or a slow look and the next tick — from looking at one rule twice; the price is that a look
    lost to a crash is lost for one interval, which is the cheap side of that trade."""
    return list(
        await conn.fetch(
            f"""
            UPDATE rules
               SET next_check_at = $1::timestamptz + make_interval(secs => poll_interval_seconds)
             WHERE id IN (
                    SELECT id FROM rules
                     WHERE enabled AND kind = 'condition' AND next_check_at <= $1::timestamptz
                     ORDER BY next_check_at
                     LIMIT $2
                       FOR UPDATE SKIP LOCKED
                   )
            RETURNING {RULE_COLUMNS}
            """,
            now,
            limit,
        )
    )


async def record_look(conn: Conn, rule_id: int, *, result: bool | None, now: datetime) -> None:
    """What a look found. `last_result` is the last look's answer, empty when none was had; `last_known_result` only ever
    takes a real answer, so it survives an outage and is what the next edge is measured against."""
    await conn.execute(
        """
        UPDATE rules
           SET last_result = $2,
               last_known_result = COALESCE($2, last_known_result),
               last_checked_at = $3
         WHERE id = $1
        """,
        rule_id,
        result,
        now,
    )


async def record_check(conn: Conn, rule_id: int, *, outcome: str, reason: str, now: datetime) -> None:
    await conn.execute(
        "INSERT INTO rule_checks (rule_id, outcome, reason, checked_at) VALUES ($1, $2, $3, $4)",
        rule_id,
        outcome,
        reason,
        now,
    )


async def last_check(conn: Conn, rule_id: int) -> asyncpg.Record | None:
    return await conn.fetchrow(
        "SELECT outcome, reason, checked_at FROM rule_checks WHERE rule_id = $1 ORDER BY checked_at DESC, id DESC LIMIT 1",
        rule_id,
    )


async def record_fire(
    conn: Conn, rule_id: int, *, edge_at: datetime, text: str, value: float | None, now: datetime
) -> int | None:
    """The rule went off. One per rule and edge — a repeat of the same edge, from another instance or a retried tick, is
    refused by the table and returns nothing — and the rule remembers when, for its cool-down."""
    fire_id = await conn.fetchval(
        """
        INSERT INTO fires (rule_id, edge_at, state, text, value, next_attempt_at, created_at)
        VALUES ($1, $2, 'pending', $3, $4, $5, $5)
        ON CONFLICT (rule_id, edge_at) DO NOTHING
        RETURNING id
        """,
        rule_id,
        edge_at,
        text,
        None if value is None else Decimal(str(value)),
        now,
    )
    if fire_id is not None:
        await conn.execute("UPDATE rules SET last_fired_at = $2 WHERE id = $1", rule_id, now)
    return fire_id
