"""What a schedule or a trigger produced when its turn came, whether or not a run started.

One table for both sources, and it carries more than a log: `runs` has no `schedule_id` or
`trigger_id` (design.md, "Trzy nowe tabele, zero zmian w tabelach fazy 1"), so a fire is the
only record of which run belongs to which schedule or trigger.
"""

from __future__ import annotations

import asyncpg
from tc_runtime.db import Conn, fetch_one

from .recurring import SCHEDULES, TRIGGERS

_INSERT_FIRE = """
    INSERT INTO schedule_fires (
        schedule_id, trigger_id, outcome, reason, run_id, skipped_count
    )
    VALUES ($1, $2, $3, $4, $5, $6)
    RETURNING id, schedule_id, trigger_id, fired_at, outcome, reason, run_id, skipped_count
"""


async def record_fire(
    conn: Conn,
    *,
    schedule_id: int | None = None,
    trigger_id: int | None = None,
    outcome: str,
    reason: str | None = None,
    run_id: int | None = None,
    skipped_count: int = 0,
) -> asyncpg.Record:
    """One row for a fire attempt from either source, whether or not it started a run —
    `outcome != 'started'` with no run at all is exactly what specs/teams-schedules asks
    to be kept ("Wyzwolenie bez przebiegu zostawia zapisany powód")."""
    return await fetch_one(
        conn, _INSERT_FIRE, schedule_id, trigger_id, outcome, reason, run_id, skipped_count
    )


async def list_fires_for_schedule(
    conn: Conn, *, schedule_id: int, owner_principal: str
) -> list[asyncpg.Record]:
    return list(await conn.fetch(SCHEDULES.select_fires, schedule_id, owner_principal))


async def list_fires_for_trigger(
    conn: Conn, *, trigger_id: int, owner_principal: str
) -> list[asyncpg.Record]:
    return list(await conn.fetch(TRIGGERS.select_fires, trigger_id, owner_principal))


async def latest_run_status_for_schedule(conn: Conn, *, schedule_id: int) -> str | None:
    """`None` when this schedule has never started a run — never mistaken for "the run
    finished", which is a real status (`completed`) and not the absence of one."""
    return await conn.fetchval(SCHEDULES.latest_run_status, schedule_id)


async def latest_run_status_for_trigger(conn: Conn, *, trigger_id: int) -> str | None:
    return await conn.fetchval(TRIGGERS.latest_run_status, trigger_id)
