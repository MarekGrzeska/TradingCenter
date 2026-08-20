"""Schedules — a team started by the clock.

Here rather than in `recurring.py` is only what a trigger has no version of: this table's
own INSERT and UPDATE. Every rule the two hold in common is one statement on `SCHEDULES`,
written once.
"""

from __future__ import annotations

from datetime import datetime

import asyncpg
from tc_runtime.db import Conn, fetch_one

from .recurring import SCHEDULE_COLUMNS, SCHEDULES

_INSERT_SCHEDULE = f"""
    INSERT INTO schedules (
        team_id, owner_principal, revision_mode, pinned_revision_id,
        cron_expression, next_fire_at
    )
    VALUES ($1, $2, $3, $4, $5, $6)
    RETURNING {SCHEDULE_COLUMNS}
"""

_UPDATE_SCHEDULE = f"""
    UPDATE schedules
       SET revision_mode = $3, pinned_revision_id = $4, cron_expression = $5,
           next_fire_at = $6, updated_at = now()
     WHERE id = $1 AND owner_principal = $2
    RETURNING {SCHEDULE_COLUMNS}
"""


async def create_schedule(
    conn: Conn,
    *,
    team_id: int,
    owner_principal: str,
    revision_mode: str,
    pinned_revision_id: int | None,
    cron_expression: str,
    next_fire_at: datetime,
) -> asyncpg.Record:
    return await fetch_one(
        conn,
        _INSERT_SCHEDULE,
        team_id,
        owner_principal,
        revision_mode,
        pinned_revision_id,
        cron_expression,
        next_fire_at,
    )


async def get_schedule(
    conn: Conn, *, schedule_id: int, owner_principal: str
) -> asyncpg.Record | None:
    return await conn.fetchrow(SCHEDULES.select, schedule_id, owner_principal)


async def list_schedules_for_team(
    conn: Conn, *, team_id: int, owner_principal: str
) -> list[asyncpg.Record]:
    return list(await conn.fetch(SCHEDULES.select_for_team, team_id, owner_principal))


async def update_schedule(
    conn: Conn,
    *,
    schedule_id: int,
    owner_principal: str,
    revision_mode: str,
    pinned_revision_id: int | None,
    cron_expression: str,
    next_fire_at: datetime,
) -> asyncpg.Record | None:
    return await conn.fetchrow(
        _UPDATE_SCHEDULE,
        schedule_id,
        owner_principal,
        revision_mode,
        pinned_revision_id,
        cron_expression,
        next_fire_at,
    )


async def set_schedule_enabled(
    conn: Conn, *, schedule_id: int, owner_principal: str, enabled: bool
) -> asyncpg.Record | None:
    return await conn.fetchrow(SCHEDULES.set_enabled, schedule_id, owner_principal, enabled)


async def delete_schedule(conn: Conn, *, schedule_id: int, owner_principal: str) -> bool:
    """Whether a row was deleted — `False` covers both "not there" and "not yours", which
    the owner filter inside the statement makes the same answer.

    The fire history goes with it, by `ON DELETE CASCADE` in migration `0007` rather than
    by a second statement here: the same rule written twice drifts the first time a caller
    forgets half of it. Runs are untouched — nothing in `runs` points at a schedule, it is
    the fire rows that point at runs (specs/teams-schedules, "Harmonogram i wyzwalacz dają
    się usunąć").
    """
    row = await conn.fetchrow(SCHEDULES.delete, schedule_id, owner_principal)
    return row is not None


async def disable_schedule_for_failures(
    conn: Conn, *, schedule_id: int, reason: str
) -> asyncpg.Record | None:
    return await conn.fetchrow(SCHEDULES.disable_for_failures, schedule_id, reason)


async def increment_schedule_failures(conn: Conn, *, schedule_id: int) -> asyncpg.Record | None:
    return await conn.fetchrow(SCHEDULES.increment_failures, schedule_id)


async def reset_schedule_failures(conn: Conn, *, schedule_id: int) -> asyncpg.Record | None:
    return await conn.fetchrow(SCHEDULES.reset_failures, schedule_id)


async def claim_due_schedule(
    conn: Conn, *, schedule_id: int, next_fire_at: datetime
) -> asyncpg.Record | None:
    """`None` means somebody else already claimed this fire, or it was disabled between
    being listed as due and this call — either way, this caller does nothing further."""
    return await conn.fetchrow(SCHEDULES.claim_due, schedule_id, next_fire_at)


async def list_due_schedules(conn: Conn) -> list[asyncpg.Record]:
    """Every enabled schedule due right now, across every owner — what one wake of the
    clock works through before attempting to claim each (specs/teams-schedules)."""
    return list(await conn.fetch(SCHEDULES.select_due))
