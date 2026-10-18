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
    id, name, kind, destination, bot, template, cooldown_seconds, mode, max_per_hour,
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
            event_type, filter, next_check_at, created_by, bot
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11, $12, $13, $14, $15, $16::jsonb, $17, $18, $19)
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
        rule.bot,
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
            bot = $19, throttle_notified_at = NULL, updated_at = now(),
            last_fired_at = CASE WHEN $7 = 'once' THEN NULL ELSE last_fired_at END
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
        rule.bot,
    )


async def set_enabled(
    conn: Conn, rule_id: int, enabled: bool, *, now: datetime
) -> asyncpg.Record | None:
    """Switched on, a value rule is looked at again at once and starts from no memory of its last result (a one-time rule
    also from its 'already told', or it would never tell again); switched off,
    it says by whom, so a rule that stopped on its own and one that was stopped read differently."""
    return await conn.fetchrow(
        f"""
        UPDATE rules SET
            enabled = $2,
            disabled_reason = CASE WHEN $2 THEN NULL ELSE 'switched off by the operator' END,
            next_check_at = CASE WHEN $2 AND kind = 'condition' THEN $3::timestamptz ELSE NULL END,
            last_result = CASE WHEN $2 THEN NULL ELSE last_result END,
            last_known_result = CASE WHEN $2 THEN NULL ELSE last_known_result END,
            last_fired_at = CASE WHEN $2 AND mode = 'once' THEN NULL ELSE last_fired_at END,
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


# --- events ---------------------------------------------------------------------------------------------------------


async def insert_event(
    conn: Conn, *, type_: str, source_key: str, attributes: dict[str, Any], text: str, now: datetime
) -> tuple[int, bool]:
    """`(id, duplicate)`. An occurrence already published is not stored again and is not an error: a producer that did not
    hear the first answer asks again, and the second answer must be the same yes."""
    created = await conn.fetchval(
        """
        INSERT INTO events (type, source_key, attributes, text, occurred_at)
        VALUES ($1, $2, $3::jsonb, $4, $5)
        ON CONFLICT (type, source_key) DO NOTHING
        RETURNING id
        """,
        type_,
        source_key,
        json.dumps(attributes),
        text,
        now,
    )
    if created is not None:
        return created, False
    existing = await conn.fetchval("SELECT id FROM events WHERE type = $1 AND source_key = $2", type_, source_key)
    # Absent only if retention removed the row between the two statements, thirty days after it was published.
    assert existing is not None
    return existing, True


async def event_rules(conn: Conn, event_type: str) -> list[asyncpg.Record]:
    """The rules that could go off for an event of this type — switched on, and of the event kind."""
    return list(
        await conn.fetch(
            f"SELECT {RULE_COLUMNS} FROM rules WHERE enabled AND kind = 'event' AND event_type = $1 ORDER BY id",
            event_type,
        )
    )


async def record_event_fire(
    conn: Conn, rule_id: int, *, event_id: int, text: str, now: datetime
) -> int | None:
    """The rule went off for this event. One per rule and event, whoever asks twice."""
    fire_id = await conn.fetchval(
        """
        INSERT INTO fires (rule_id, event_id, state, text, next_attempt_at, created_at)
        VALUES ($1, $2, 'pending', $3, $4, $4)
        ON CONFLICT (rule_id, event_id) DO NOTHING
        RETURNING id
        """,
        rule_id,
        event_id,
        text,
        now,
    )
    if fire_id is not None:
        await conn.execute("UPDATE rules SET last_fired_at = $2 WHERE id = $1", rule_id, now)
    return fire_id


async def delete_events_before(conn: Conn, before: datetime) -> int:
    """Events past their retention. The fires they caused are kept: the text that was sent is the record."""
    result = await conn.execute("DELETE FROM events WHERE occurred_at < $1", before)
    return int(result.rsplit(" ", 1)[-1])


# --- delivery -------------------------------------------------------------------------------------------------------


async def claim_deliveries(conn: Conn, *, now: datetime, limit: int, lease_seconds: int) -> list[asyncpg.Record]:
    """The fires waiting to be sent, each leased for a minute in the same statement. The lease is what keeps two ticks —
    or two instances — from sending one message twice; a crash in the middle leaves the fire to be tried again once the
    lease runs out, which is a message possibly told twice and never one lost."""
    return list(
        await conn.fetch(
            """
            WITH due AS (
                SELECT id FROM fires
                 WHERE state = 'pending' AND next_attempt_at <= $1::timestamptz
                 ORDER BY next_attempt_at
                 LIMIT $2
                   FOR UPDATE SKIP LOCKED
            ), leased AS (
                UPDATE fires f
                   SET attempts = f.attempts + 1,
                       next_attempt_at = $1::timestamptz + make_interval(secs => $3)
                  FROM due
                 WHERE f.id = due.id
             RETURNING f.id, f.rule_id, f.text, f.created_at, f.attempts
            )
            SELECT leased.*, r.name AS rule_name, r.destination, r.bot, r.mode, r.enabled, r.max_per_hour
              FROM leased JOIN rules r ON r.id = leased.rule_id
            """,
            now,
            limit,
            lease_seconds,
        )
    )


async def settle_fire(
    conn: Conn, fire_id: int, *, state: str, reason: str | None = None, now: datetime | None = None
) -> None:
    """The fire's last word. `delivered_at` is set only for a delivery."""
    await conn.execute(
        """
        UPDATE fires
           SET state = $2, reason = $3, next_attempt_at = NULL,
               delivered_at = CASE WHEN $2 = 'delivered' THEN $4::timestamptz END
         WHERE id = $1
        """,
        fire_id,
        state,
        reason,
        now,
    )


async def retry_fire(conn: Conn, fire_id: int, *, at: datetime, reason: str) -> None:
    await conn.execute("UPDATE fires SET next_attempt_at = $2, reason = $3 WHERE id = $1", fire_id, at, reason)


async def delivered_since(conn: Conn, rule_id: int, since: datetime) -> int:
    counted = await conn.fetchval(
        "SELECT count(*) FROM fires WHERE rule_id = $1 AND state = 'delivered' AND delivered_at > $2", rule_id, since
    )
    return counted or 0


async def throttled_since(conn: Conn, rule_id: int, since: datetime) -> int:
    counted = await conn.fetchval(
        "SELECT count(*) FROM fires WHERE rule_id = $1 AND state = 'throttled' AND created_at > $2", rule_id, since
    )
    return counted or 0


async def claim_throttle_notice(conn: Conn, rule_id: int, *, now: datetime, since: datetime) -> bool:
    """Whether this caller is the one to tell the operator the rule is throttled: one statement decides, so the fires of a
    batch that are all throttled together say it once between them."""
    claimed = await conn.fetchval(
        """
        UPDATE rules SET throttle_notified_at = $2
         WHERE id = $1 AND (throttle_notified_at IS NULL OR throttle_notified_at < $3)
        RETURNING id
        """,
        rule_id,
        now,
        since,
    )
    return claimed is not None


async def release_throttle_notice(conn: Conn, rule_id: int) -> None:
    """The notice did not go; the next throttled fire may try."""
    await conn.execute("UPDATE rules SET throttle_notified_at = NULL WHERE id = $1", rule_id)


async def finish_once_rule(conn: Conn, rule_id: int, reason: str) -> None:
    """A one-time rule that has said its one thing: switched off, with the reason, and not looked at again."""
    await conn.execute(
        "UPDATE rules SET enabled = false, disabled_reason = $2, next_check_at = NULL, updated_at = now() WHERE id = $1",
        rule_id,
        reason,
    )


async def reopen_once_rule(conn: Conn, rule_id: int) -> None:
    """A one-time rule whose one alert never arrived may fire again: its 'already told' is taken back."""
    await conn.execute("UPDATE rules SET last_fired_at = NULL WHERE id = $1 AND mode = 'once'", rule_id)


# --- drafts ---------------------------------------------------------------------------------------------------------


async def record_draft_usage(conn: Conn, *, model: str, input_tokens: int, output_tokens: int, now: datetime) -> None:
    await conn.execute(
        "INSERT INTO draft_usage (at, model, input_tokens, output_tokens) VALUES ($1, $2, $3, $4)",
        now,
        model,
        input_tokens,
        output_tokens,
    )


async def draft_tokens_since(conn: Conn, since: datetime) -> int:
    spent = await conn.fetchval("SELECT coalesce(sum(input_tokens + output_tokens), 0) FROM draft_usage WHERE at >= $1", since)
    return int(spent or 0)


# --- what happened, and how things stand ----------------------------------------------------------------------------


async def recent_fires(conn: Conn, rule_id: int, limit: int) -> list[asyncpg.Record]:
    return list(
        await conn.fetch(
            "SELECT created_at, state, reason, text FROM fires WHERE rule_id = $1 ORDER BY created_at DESC, id DESC LIMIT $2",
            rule_id,
            limit,
        )
    )


async def recent_checks(conn: Conn, rule_id: int, limit: int) -> list[asyncpg.Record]:
    return list(
        await conn.fetch(
            "SELECT checked_at, outcome, reason FROM rule_checks WHERE rule_id = $1 ORDER BY checked_at DESC, id DESC LIMIT $2",
            rule_id,
            limit,
        )
    )


async def standing(conn: Conn) -> asyncpg.Record:
    """The numbers `/state` reports, in one read of two small tables: the rules (a list an operator wrote by hand) and the
    fires still waiting (an index on exactly those)."""
    return await fetch_one(
        conn,
        """
        SELECT
            (SELECT count(*) FROM rules WHERE enabled) AS enabled,
            (SELECT count(*) FROM rules WHERE NOT enabled) AS disabled,
            (SELECT count(*) FROM rules WHERE defect IS NOT NULL) AS drifted,
            (SELECT count(*) FROM fires WHERE state = 'pending') AS waiting,
            (SELECT count(*) FROM event_types) AS event_types
        """,
    )


async def destinations_in_use(conn: Conn) -> set[str]:
    return {row["destination"] for row in await conn.fetch("SELECT DISTINCT destination FROM rules")}


async def rule_targets(conn: Conn) -> list[asyncpg.Record]:
    """Where every rule would tell and whether its own schema still fits: what the state needs to count rules with
    something wrong, one row per rule."""
    return list(await conn.fetch("SELECT id, destination, bot, defect FROM rules"))


async def seen_values(conn: Conn, event_type: str, attribute: str, limit: int = 50) -> list[str]:
    """The values this attribute has had in retained events, most frequent first: what the form offers instead of a blank."""
    rows = await conn.fetch(
        """
        SELECT attributes ->> $2 AS value
          FROM events
         WHERE type = $1 AND attributes ->> $2 IS NOT NULL AND attributes ->> $2 <> ''
         GROUP BY 1
         ORDER BY count(*) DESC, 1
         LIMIT $3
        """,
        event_type,
        attribute,
        limit,
    )
    return [row["value"] for row in rows]

