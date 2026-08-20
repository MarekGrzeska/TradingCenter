"""Runs, their steps, and what those steps called — with the recovery that closes what a
dead process left behind.

The owner is on `runs` itself rather than reached through the revision → team chain: a
run's access check must not depend on a join, and a retired team's runs stay readable
(specs/teams-browser-access).
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import asyncpg
from tc_runtime.db import Conn, fetch_one

_INSERT_RUN = """
    INSERT INTO runs (team_revision_id, owner_principal)
    VALUES ($1, $2)
    RETURNING id, team_revision_id, status, stopped_reason, started_at, finished_at, created_at
"""

_INSERT_STEP = """
    INSERT INTO run_steps (run_id, agent_key)
    VALUES ($1, $2)
    RETURNING id, run_id, agent_key, status, output, rounds, started_at, finished_at
"""

_SELECT_RUN = """
    SELECT id, team_revision_id, status, stopped_reason, started_at, finished_at, created_at
      FROM runs
     WHERE id = $1 AND owner_principal = $2
"""

# No owner filter — the caller already knows the run by an id it resolved itself (the
# schedule/trigger clock, tracking a run it started, and matching `list_due_schedules`'
# own reach across every owner). Not `get_run`'s job: that one exists precisely to
# refuse a stranger's run, and this one has no stranger to refuse.
_SELECT_RUN_STATUS = """
    SELECT status FROM runs WHERE id = $1
"""

# Every run of one team, newest first — the runs of *all* its revisions, because that is
# the comparison the module exists for (design.md, "Dwa przebiegi tej samej rewizji mają
# być porównywalne", and two of different ones are the other half of it).
_SELECT_RUNS_FOR_TEAM = """
    SELECT r.id, r.team_revision_id, r.status, r.stopped_reason, r.started_at,
           r.finished_at, r.created_at
      FROM runs r
      JOIN team_revisions v ON v.id = r.team_revision_id
     WHERE v.team_id = $1 AND r.owner_principal = $2
     ORDER BY r.created_at DESC, r.id DESC
"""

_SELECT_STEPS = """
    SELECT id, run_id, agent_key, status, output, rounds, started_at, finished_at
      FROM run_steps
     WHERE run_id = $1
     ORDER BY id
"""

_SELECT_RUN_TOOL_CALLS = """
    SELECT id, run_step_id, round_index, position, tool_name, arguments, outcome,
           result_text, duration_ms, created_at
      FROM tool_calls
     WHERE run_id = $1
     ORDER BY run_step_id, round_index, position
"""

_MARK_RUN_RUNNING = """
    UPDATE runs SET status = 'running', started_at = now()
     WHERE id = $1 AND status = 'pending'
    RETURNING id
"""

# `status IN ('pending', 'running')` guards the second writer: an operator's interruption
# and the time limit can land together, and whichever arrives first is the reason the run
# keeps. Without it the later one would overwrite a finished run's own account of itself.
_FINISH_RUN = """
    UPDATE runs
       SET status = $2, stopped_reason = $3, finished_at = now()
     WHERE id = $1 AND status IN ('pending', 'running')
    RETURNING id, team_revision_id, status, stopped_reason, started_at, finished_at, created_at
"""

_START_STEP = """
    UPDATE run_steps SET status = 'running', started_at = now()
     WHERE run_id = $1 AND agent_key = $2
    RETURNING id, run_id, agent_key, status, output, rounds, started_at, finished_at
"""

_FINISH_STEP = """
    UPDATE run_steps
       SET status = $2, output = $3, rounds = $4, finished_at = now()
     WHERE id = $1
    RETURNING id, run_id, agent_key, status, output, rounds, started_at, finished_at
"""

_INSERT_TOOL_CALL = """
    INSERT INTO tool_calls (
        run_id, run_step_id, round_index, position,
        tool_name, arguments, outcome, result_text, duration_ms
    )
    VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9)
    RETURNING id, run_step_id, round_index, position, tool_name, arguments, outcome,
              result_text, duration_ms, created_at
"""


# Recovery, run once at start-up. A run marked `running` in the database with no task
# behind it is a run whose process died — this module keeps a run in memory, so nothing
# will ever move it again (specs/teams-runs, and `app.py`'s lifespan is the caller).
# Steps first: a step left `running` under a run being closed would keep claiming an agent
# is working.
_FAIL_ORPHAN_STEPS = """
    UPDATE run_steps SET status = 'failed', finished_at = now()
     WHERE status IN ('pending', 'running')
       AND run_id IN (SELECT id FROM runs WHERE status IN ('pending', 'running'))
"""

# The same idea for one run that is ending now: a step still `running` stops when its run
# does. A step still `pending` is left alone — it never started, and marking it failed
# would put work in the trace nobody attempted.
_FAIL_RUNNING_STEPS = """
    UPDATE run_steps SET status = 'failed', finished_at = now()
     WHERE run_id = $1 AND status = 'running'
"""

_FAIL_ORPHAN_RUNS = """
    UPDATE runs
       SET status = 'failed', stopped_reason = $1, finished_at = now()
     WHERE status IN ('pending', 'running')
    RETURNING id
"""


async def create_run(
    conn: Conn, *, team_revision_id: int, owner_principal: str, agent_keys: Sequence[str]
) -> tuple[asyncpg.Record, list[asyncpg.Record]]:
    """The run and one pending step per agent, in one transaction.

    Every step exists before the first model call, rather than appearing as its agent
    starts: an operator watching the run has to see who is waiting, not only who is
    working (specs/teams-runs, "odbierający postęp widzi, który agent pracuje, a który
    czeka").
    """
    async with conn.transaction():
        run = await fetch_one(conn, _INSERT_RUN, team_revision_id, owner_principal)
        steps = [await fetch_one(conn, _INSERT_STEP, run["id"], key) for key in agent_keys]
    return run, steps


async def get_run(conn: Conn, *, run_id: int, owner_principal: str) -> asyncpg.Record | None:
    return await conn.fetchrow(_SELECT_RUN, run_id, owner_principal)


async def get_run_status(conn: Conn, *, run_id: int) -> str | None:
    return await conn.fetchval(_SELECT_RUN_STATUS, run_id)


async def list_runs_for_team(
    conn: Conn, *, team_id: int, owner_principal: str
) -> list[asyncpg.Record]:
    return list(await conn.fetch(_SELECT_RUNS_FOR_TEAM, team_id, owner_principal))


async def get_run_steps(conn: Conn, *, run_id: int) -> list[asyncpg.Record]:
    return list(await conn.fetch(_SELECT_STEPS, run_id))


async def get_run_tool_calls(conn: Conn, *, run_id: int) -> list[asyncpg.Record]:
    return list(await conn.fetch(_SELECT_RUN_TOOL_CALLS, run_id))


async def mark_run_running(conn: Conn, *, run_id: int) -> bool:
    return await conn.fetchrow(_MARK_RUN_RUNNING, run_id) is not None


async def finish_run(
    conn: Conn, *, run_id: int, status: str, stopped_reason: str | None
) -> asyncpg.Record | None:
    """Closes a run once. A second caller — the time limit arriving just after the
    operator's interruption — gets `None` and leaves the first account standing."""
    return await conn.fetchrow(_FINISH_RUN, run_id, status, stopped_reason)


async def start_step(conn: Conn, *, run_id: int, agent_key: str) -> asyncpg.Record:
    return await fetch_one(conn, _START_STEP, run_id, agent_key)


async def finish_step(
    conn: Conn, *, step_id: int, status: str, output: str | None, rounds: int
) -> asyncpg.Record:
    return await fetch_one(conn, _FINISH_STEP, step_id, status, output, rounds)


async def record_tool_call(
    conn: Conn,
    *,
    run_id: int,
    run_step_id: int,
    round_index: int,
    position: int,
    tool_name: str,
    arguments: dict,
    outcome: str,
    result_text: str,
    duration_ms: int,
) -> asyncpg.Record:
    """Written as the call resolves, not when the agent finishes — a run that breaks in
    the middle keeps every call it made (specs/teams-runs)."""
    return await fetch_one(
        conn,
        _INSERT_TOOL_CALL,
        run_id,
        run_step_id,
        round_index,
        position,
        tool_name,
        json.dumps(arguments),
        outcome,
        result_text,
        duration_ms,
    )


async def fail_running_steps(conn: Conn, *, run_id: int) -> None:
    await conn.execute(_FAIL_RUNNING_STEPS, run_id)


async def fail_unfinished_runs(conn: Conn, *, reason: str) -> list[int]:
    """Closes runs left open by a process that died, and returns their ids for the log.

    A run lives in the process that started it, so a restart leaves nothing that could
    ever move these rows again. Closing them at start-up is what keeps a dead run from
    reading as a working one for the rest of the module's life.
    """
    async with conn.transaction():
        await conn.execute(_FAIL_ORPHAN_STEPS)
        rows = await conn.fetch(_FAIL_ORPHAN_RUNS, reason)
    return [row["id"] for row in rows]
