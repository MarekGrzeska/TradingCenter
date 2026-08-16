"""Reading and writing the catalogue — the only door to `teams` and `team_revisions`,
same shape as `agent/store.py` and `market_data/store.py`: asyncpg directly, no ORM in
the runtime path.

Two properties ride on every function here rather than on the routes that call them, so
that no route can forget one:

- **the owner filter is part of the statement.** A team belonging to somebody else and a
  team that was never created answer identically — `None`, no row, nothing to tell them
  apart by (specs/teams-browser-access, "Odmowa dostępu do cudzego zespołu MUST być
  nieodróżnialna od odpowiedzi o zespole nieistniejącym");
- **`team_revisions` is only ever inserted into.** There is no UPDATE statement against
  it in this file and there should never be one: a run points at a revision, and a
  revision edited underneath a finished run turns its trace into a claim about a team
  that no longer exists (specs/teams-catalogue, "Rewizja raz zapisana się nie zmienia").

Rows come back as `asyncpg.Record` and go to `contract.py`'s `from_row` unchanged — see
that file's docstring for why this module has no domain layer in between.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from decimal import Decimal

import asyncpg

from .contract import TeamDefinition
from .db import Conn, fetch_one

# `latest_revision` is derived rather than stored on `teams`. The correlated subquery
# reads one row from `ix_team_revisions_team_version` per team — a catalogue is tens of
# rows, not millions — and the alternative is a denormalized column that two writers
# could disagree about. The listing still loads no definition, which is the property
# specs/teams-catalogue actually asks for ("lista powstaje bez pobierania definicji").
_LATEST_REVISION = """
    (SELECT max(r.version) FROM team_revisions r WHERE r.team_id = t.id) AS latest_revision
"""

_INSERT_TEAM = """
    INSERT INTO teams (owner_principal, name, description)
    VALUES ($1, $2, $3)
    RETURNING id, name, description, created_at, updated_at
"""

_INSERT_REVISION = """
    INSERT INTO team_revisions (team_id, version, definition)
    VALUES ($1, $2, $3)
    RETURNING id, team_id, version, definition, created_at
"""

# `archived_at IS NULL` rides on every read of a team, here and below: a retired team is
# gone from the catalogue an operator picks a run from, and answers a direct read the way
# a deleted one would — while its revisions stay readable through the statements further
# down (specs/teams-catalogue, "Zespół wycofany z katalogu nie zabiera ze sobą przebiegów").
_SELECT_TEAM = f"""
    SELECT t.id, t.name, t.description, t.created_at, t.updated_at, {_LATEST_REVISION}
      FROM teams t
     WHERE t.id = $1 AND t.owner_principal = $2 AND t.archived_at IS NULL
"""

_SELECT_TEAMS_FOR_OWNER = f"""
    SELECT t.id, t.name, t.description, t.created_at, t.updated_at, {_LATEST_REVISION}
      FROM teams t
     WHERE t.owner_principal = $1 AND t.archived_at IS NULL
     ORDER BY t.updated_at DESC, t.id DESC
"""

# `FOR UPDATE` on the team row, not on `team_revisions`: two saves arriving together
# would otherwise both read the same `max(version)` and one would lose to the unique
# constraint. The lock is held for the length of one insert on a single-operator table.
_LOCK_TEAM_FOR_WRITE = """
    SELECT id FROM teams
     WHERE id = $1 AND owner_principal = $2 AND archived_at IS NULL
       FOR UPDATE
"""

_NEXT_VERSION = """
    SELECT coalesce(max(version), 0) + 1 AS version FROM team_revisions WHERE team_id = $1
"""

# "Moment ostatniej zmiany" in the catalogue listing — bumped by the application because
# nothing else writes to the row when a revision lands.
_TOUCH_TEAM = """
    UPDATE teams SET updated_at = now() WHERE id = $1
"""

# Ownership through the join rather than through `archived_at`: a revision belongs to
# whoever owns the team, and stays readable after that team is retired, because a run
# points at it.
_SELECT_REVISION = """
    SELECT r.id, r.team_id, r.version, r.definition, r.created_at
      FROM team_revisions r
      JOIN teams t ON t.id = r.team_id
     WHERE r.team_id = $1 AND t.owner_principal = $2 AND r.version = $3
"""

_SELECT_LATEST_REVISION = """
    SELECT r.id, r.team_id, r.version, r.definition, r.created_at
      FROM team_revisions r
      JOIN teams t ON t.id = r.team_id
     WHERE r.team_id = $1 AND t.owner_principal = $2
     ORDER BY r.version DESC
     LIMIT 1
"""

# `archived_at IS NULL` in the WHERE, not only in the stamp: retiring twice returns no
# row, so the route answers 404 the second time rather than quietly moving the timestamp.
# An UPDATE, never a DELETE — the runs and revisions hanging off this team are the result
# of the experiment this module exists to keep.
_ARCHIVE_TEAM = """
    UPDATE teams SET archived_at = now()
     WHERE id = $1 AND owner_principal = $2 AND archived_at IS NULL
    RETURNING id
"""


def _as_jsonb(definition: TeamDefinition) -> str:
    """`by_alias=True` is load-bearing: `TeamEdge.from_` is written `from` on the wire and
    MUST be written `from` in storage too, so that a revision read back parses through the
    same alias rather than through the populate-by-name fallback."""
    return json.dumps(definition.model_dump(mode="json", by_alias=True))


async def create_team(
    conn: Conn,
    *,
    owner_principal: str,
    name: str,
    description: str,
    definition: TeamDefinition,
) -> tuple[asyncpg.Record, asyncpg.Record]:
    """The team and its first revision, in one transaction. A team with no revision would
    be a catalogue entry that cannot be opened or run, and `TeamOut.latest_revision` has
    nowhere to get a value from — so the two rows are written together or not at all."""
    async with conn.transaction():
        team = await fetch_one(conn, _INSERT_TEAM, owner_principal, name, description)
        revision = await fetch_one(conn, _INSERT_REVISION, team["id"], 1, _as_jsonb(definition))
    return team, revision


async def save_revision(
    conn: Conn, *, team_id: int, owner_principal: str, definition: TeamDefinition
) -> asyncpg.Record | None:
    """The next revision of a team, or `None` for one that does not exist, belongs to
    somebody else, or was retired. Nothing about the previous revision is touched."""
    async with conn.transaction():
        locked = await conn.fetchrow(_LOCK_TEAM_FOR_WRITE, team_id, owner_principal)
        if locked is None:
            return None
        version = await fetch_one(conn, _NEXT_VERSION, team_id)
        revision = await fetch_one(
            conn, _INSERT_REVISION, team_id, version["version"], _as_jsonb(definition)
        )
        await conn.execute(_TOUCH_TEAM, team_id)
    return revision


async def get_team(conn: Conn, *, team_id: int, owner_principal: str) -> asyncpg.Record | None:
    return await conn.fetchrow(_SELECT_TEAM, team_id, owner_principal)


async def list_teams(conn: Conn, *, owner_principal: str) -> list[asyncpg.Record]:
    return list(await conn.fetch(_SELECT_TEAMS_FOR_OWNER, owner_principal))


async def get_revision(
    conn: Conn, *, team_id: int, owner_principal: str, version: int
) -> asyncpg.Record | None:
    """A revision exactly as it was saved, including one of a team since retired — that is
    what makes an old run's trace mean anything (specs/teams-catalogue)."""
    return await conn.fetchrow(_SELECT_REVISION, team_id, owner_principal, version)


async def get_latest_revision(
    conn: Conn, *, team_id: int, owner_principal: str
) -> asyncpg.Record | None:
    return await conn.fetchrow(_SELECT_LATEST_REVISION, team_id, owner_principal)


async def archive_team(conn: Conn, *, team_id: int, owner_principal: str) -> bool:
    """Retires a team from the catalogue. Its revisions and every run that pointed at
    them stay exactly where they were — see `_ARCHIVE_TEAM`."""
    row = await conn.fetchrow(_ARCHIVE_TEAM, team_id, owner_principal)
    return row is not None


# --- runs, their steps, and what those steps called ---------------------------------
#
# The owner is on `runs` itself rather than reached through the revision → team chain: a
# run's access check must not depend on a join, and a retired team's runs stay readable
# (specs/teams-browser-access).

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

_INSERT_USAGE = """
    INSERT INTO usage (
        run_id, run_step_id, model_id,
        input_tokens, output_tokens, cached_tokens, reasoning_tokens,
        input_rate_per_1m, output_rate_per_1m, cost
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
    RETURNING id, run_id, run_step_id, model_id, input_tokens, output_tokens,
              cached_tokens, reasoning_tokens, cost, created_at
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


async def record_usage(
    conn: Conn,
    *,
    run_id: int,
    run_step_id: int,
    model_id: str,
    input_tokens: int | None,
    output_tokens: int | None,
    cached_tokens: int | None,
    reasoning_tokens: int | None,
    input_rate_per_1m: Decimal,
    output_rate_per_1m: Decimal,
) -> asyncpg.Record:
    """The one place a cost is computed, and the only moment it ever is — never again at
    read time (specs/teams-usage, "Koszt jest przypisany do wiersza w chwili zapisu").

    A call the provider reported nothing for leaves a row with no tokens and no cost: the
    call happened and is part of the trace, and a zero there would be a claim that it was
    free (specs/teams-usage, "Brak informacji o zużyciu jest zapisany jako brak").
    """
    cost = None
    if input_tokens is not None and output_tokens is not None:
        cost = (Decimal(input_tokens) / 1_000_000 * input_rate_per_1m) + (
            Decimal(output_tokens) / 1_000_000 * output_rate_per_1m
        )
    return await fetch_one(
        conn,
        _INSERT_USAGE,
        run_id,
        run_step_id,
        model_id,
        input_tokens,
        output_tokens,
        cached_tokens,
        reasoning_tokens,
        input_rate_per_1m,
        output_rate_per_1m,
        cost,
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
