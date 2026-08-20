"""Triggers — a team started by a condition being met.

The half a schedule has no version of: this table's own INSERT and UPDATE, and
`record_trigger_check`, the one statement neither shares. The rest is `TRIGGERS`.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal

import asyncpg
from tc_runtime.db import Conn, fetch_one

from .recurring import TRIGGER_COLUMNS, TRIGGERS

_INSERT_TRIGGER = f"""
    INSERT INTO triggers (
        team_id, owner_principal, revision_mode, pinned_revision_id,
        tool_name, arguments, field_path, comparison, threshold,
        cooldown_seconds, poll_interval_seconds, next_check_at
    )
    VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, $10, $11, $12)
    RETURNING {TRIGGER_COLUMNS}
"""

_UPDATE_TRIGGER = f"""
    UPDATE triggers
       SET revision_mode = $3, pinned_revision_id = $4, tool_name = $5,
           arguments = $6::jsonb, field_path = $7, comparison = $8, threshold = $9,
           cooldown_seconds = $10, poll_interval_seconds = $11,
           updated_at = now()
     WHERE id = $1 AND owner_principal = $2
    RETURNING {TRIGGER_COLUMNS}
"""

# The edge-detection state itself: what the condition answered, and when it last fired.
# `result` is `NULL` when the tool server could not be asked at all — a third value, not
# a `false` (specs/teams-triggers, "Niedostępność serwera narzędzi to nie jest niespełniony
# warunek") — so this statement, not the caller's Python, is what a reader trusts for
# "was this ever actually evaluated". The one statement in this half with no counterpart
# on the other: a schedule has nothing to evaluate.
_RECORD_TRIGGER_CHECK = f"""
    UPDATE triggers
       SET last_result = $2,
           last_checked_at = now(),
           last_fired_at = CASE WHEN $3 THEN now() ELSE last_fired_at END,
           updated_at = now()
     WHERE id = $1
    RETURNING {TRIGGER_COLUMNS}
"""


async def create_trigger(
    conn: Conn,
    *,
    team_id: int,
    owner_principal: str,
    revision_mode: str,
    pinned_revision_id: int | None,
    tool_name: str,
    arguments: dict,
    field_path: str,
    comparison: str,
    threshold: Decimal,
    cooldown_seconds: int,
    poll_interval_seconds: int,
    next_check_at: datetime,
) -> asyncpg.Record:
    return await fetch_one(
        conn,
        _INSERT_TRIGGER,
        team_id,
        owner_principal,
        revision_mode,
        pinned_revision_id,
        tool_name,
        json.dumps(arguments),
        field_path,
        comparison,
        threshold,
        cooldown_seconds,
        poll_interval_seconds,
        next_check_at,
    )


async def get_trigger(
    conn: Conn, *, trigger_id: int, owner_principal: str
) -> asyncpg.Record | None:
    return await conn.fetchrow(TRIGGERS.select, trigger_id, owner_principal)


async def list_triggers_for_team(
    conn: Conn, *, team_id: int, owner_principal: str
) -> list[asyncpg.Record]:
    return list(await conn.fetch(TRIGGERS.select_for_team, team_id, owner_principal))


async def update_trigger(
    conn: Conn,
    *,
    trigger_id: int,
    owner_principal: str,
    revision_mode: str,
    pinned_revision_id: int | None,
    tool_name: str,
    arguments: dict,
    field_path: str,
    comparison: str,
    threshold: Decimal,
    cooldown_seconds: int,
    poll_interval_seconds: int,
) -> asyncpg.Record | None:
    return await conn.fetchrow(
        _UPDATE_TRIGGER,
        trigger_id,
        owner_principal,
        revision_mode,
        pinned_revision_id,
        tool_name,
        json.dumps(arguments),
        field_path,
        comparison,
        threshold,
        cooldown_seconds,
        poll_interval_seconds,
    )


async def set_trigger_enabled(
    conn: Conn, *, trigger_id: int, owner_principal: str, enabled: bool
) -> asyncpg.Record | None:
    return await conn.fetchrow(TRIGGERS.set_enabled, trigger_id, owner_principal, enabled)


async def delete_trigger(conn: Conn, *, trigger_id: int, owner_principal: str) -> bool:
    """The same as `delete_schedule`, for the other half of the pair — including the fire
    history going with it and the runs staying."""
    row = await conn.fetchrow(TRIGGERS.delete, trigger_id, owner_principal)
    return row is not None


async def disable_trigger_for_failures(
    conn: Conn, *, trigger_id: int, reason: str
) -> asyncpg.Record | None:
    return await conn.fetchrow(TRIGGERS.disable_for_failures, trigger_id, reason)


async def increment_trigger_failures(conn: Conn, *, trigger_id: int) -> asyncpg.Record | None:
    return await conn.fetchrow(TRIGGERS.increment_failures, trigger_id)


async def reset_trigger_failures(conn: Conn, *, trigger_id: int) -> asyncpg.Record | None:
    return await conn.fetchrow(TRIGGERS.reset_failures, trigger_id)


async def claim_trigger_for_check(
    conn: Conn, *, trigger_id: int, next_check_at: datetime
) -> asyncpg.Record | None:
    """`None` means another process is already evaluating this trigger's next check, or
    it was disabled in between — mirrors `claim_due_schedule`."""
    return await conn.fetchrow(TRIGGERS.claim_due, trigger_id, next_check_at)


async def list_due_triggers(conn: Conn) -> list[asyncpg.Record]:
    """Every enabled trigger due for a check right now, across every owner — mirrors
    `list_due_schedules`."""
    return list(await conn.fetch(TRIGGERS.select_due))


async def record_trigger_check(
    conn: Conn, *, trigger_id: int, result: bool | None, fired: bool
) -> asyncpg.Record:
    return await fetch_one(conn, _RECORD_TRIGGER_CHECK, trigger_id, result, fired)
