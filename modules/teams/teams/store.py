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
from datetime import datetime
from decimal import Decimal

import asyncpg
from tc_runtime.db import Conn, fetch_one

from .contract import TeamDefinition

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

# By id rather than by team and version: this is what a *run* names (`runs.team_revision_id`),
# and a viewer watching one has the run in hand and nothing else. Going through the version
# would mean asking the run's team which version this is — a question whose only honest
# answer is this row.
_SELECT_REVISION_BY_ID = """
    SELECT r.id, r.team_id, r.version, r.definition, r.created_at
      FROM team_revisions r
      JOIN teams t ON t.id = r.team_id
     WHERE r.id = $1 AND t.owner_principal = $2
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


async def get_revision_by_id(
    conn: Conn, *, revision_id: int, owner_principal: str
) -> asyncpg.Record | None:
    """The revision a run points at, fetched the way the run names it."""
    return await conn.fetchrow(_SELECT_REVISION_BY_ID, revision_id, owner_principal)


async def get_latest_revision(
    conn: Conn, *, team_id: int, owner_principal: str
) -> asyncpg.Record | None:
    return await conn.fetchrow(_SELECT_LATEST_REVISION, team_id, owner_principal)


async def archive_team(conn: Conn, *, team_id: int, owner_principal: str) -> bool:
    """Retires a team from the catalogue. Its revisions and every run that pointed at
    them stay exactly where they were — see `_ARCHIVE_TEAM`."""
    row = await conn.fetchrow(_ARCHIVE_TEAM, team_id, owner_principal)
    return row is not None


# --- where the operator put each agent ------------------------------------------------
#
# Mutable, beside the revisions rather than inside them: dragging a node MUST NOT mint a
# revision (specs/terminal-teams, "Przesunięcie nie jest zmianą definicji"). The owner is
# reached through the team, which is also what makes a stranger's write a no-op rather
# than a refusal in a second place.

_SELECT_LAYOUT = """
    SELECT l.agent_key, l.x, l.y
      FROM team_layouts l
      JOIN teams t ON t.id = l.team_id
     WHERE l.team_id = $1 AND t.owner_principal = $2
     ORDER BY l.agent_key
"""

# The whole layout arrives at once and replaces what was there: the canvas knows where
# every node it drew stands, and an agent deleted from the definition has to lose its row
# rather than sit in the way of a key reused later.
_DELETE_LAYOUT = "DELETE FROM team_layouts WHERE team_id = $1"

_UPSERT_PLACE = """
    INSERT INTO team_layouts (team_id, agent_key, x, y)
    VALUES ($1, $2, $3, $4)
"""


async def get_layout(
    conn: Conn, *, team_id: int, owner_principal: str
) -> list[asyncpg.Record]:
    return list(await conn.fetch(_SELECT_LAYOUT, team_id, owner_principal))


async def save_layout(
    conn: Conn, *, team_id: int, owner_principal: str, places: Sequence[tuple[str, float, float]]
) -> bool:
    """Replaces this team's layout. `False` for a team that does not exist or belongs to
    somebody else — the route answers that the same way it answers a missing team.

    `updated_at` on the team is deliberately not touched: the catalogue's "moment ostatniej
    zmiany" is about the definition, and a column that moved because a node was nudged
    would make the list reorder itself for nothing.
    """
    async with conn.transaction():
        team = await conn.fetchrow(_SELECT_TEAM, team_id, owner_principal)
        if team is None:
            return False
        await conn.execute(_DELETE_LAYOUT, team_id)
        for agent_key, x, y in places:
            await conn.execute(_UPSERT_PLACE, team_id, agent_key, x, y)
    return True


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


# --- what it all cost ----------------------------------------------------------------
#
# Every read here sums `cost` as it was written. Nothing recomputes from tokens and rates:
# a cennik changed after a run MUST NOT reprice it (specs/teams-usage, "Koszt jest
# przypisany do wiersza w chwili zapisu"), and a SUM over a column is the only shape that
# cannot accidentally do otherwise.
#
# `owner_principal` rides on `runs`, so every one of these is owner-scoped without a join
# through the catalogue — and a retired team's runs still answer.

_TEAM_COST_SINCE = """
    SELECT COALESCE(SUM(u.cost), 0) AS total
      FROM usage u
      JOIN runs r ON r.id = u.run_id
      JOIN team_revisions v ON v.id = r.team_revision_id
     WHERE v.team_id = $1 AND r.owner_principal = $2 AND u.created_at >= $3
"""

# `unknown_count` is what keeps a total honest: rows the provider reported no tokens for
# are counted, not dropped and not summed as zero, so an operator can see that a number is
# a floor rather than the whole bill (specs/teams-usage, "Brak informacji o zużyciu").
_AGGREGATE_COLUMNS = """
           COALESCE(SUM(u.input_tokens), 0)::bigint AS input_tokens,
           COALESCE(SUM(u.output_tokens), 0)::bigint AS output_tokens,
           COALESCE(SUM(u.cost), 0) AS cost,
           COUNT(*) FILTER (WHERE u.cost IS NULL)::bigint AS unknown_count
"""

_USAGE_FILTER = """
      FROM usage u
      JOIN runs r ON r.id = u.run_id
      JOIN run_steps s ON s.id = u.run_step_id
      JOIN team_revisions v ON v.id = r.team_revision_id
     WHERE r.owner_principal = $1
       AND ($2::bigint IS NULL OR r.id = $2)
       AND ($3::bigint IS NULL OR v.team_id = $3)
"""

_USAGE_BY_AGENT = f"""
    SELECT s.agent_key AS key, {_AGGREGATE_COLUMNS}
    {_USAGE_FILTER}
     GROUP BY s.agent_key
     ORDER BY s.agent_key
"""

_USAGE_BY_MODEL = f"""
    SELECT u.model_id AS key, {_AGGREGATE_COLUMNS}
    {_USAGE_FILTER}
     GROUP BY u.model_id
     ORDER BY u.model_id
"""

_USAGE_TOTAL = f"""
    SELECT COALESCE(SUM(u.cost), 0) AS total
    {_USAGE_FILTER}
"""


async def team_cost_since(
    conn: Conn, *, team_id: int, owner_principal: str, since: datetime
) -> Decimal:
    """What this team's runs have cost since a moment — the daily ceiling's own question
    (specs/teams-usage, "granicę kosztu dobowego dla zespołu")."""
    # COALESCE in the statement means a team with no runs answers 0 rather than NULL;
    # the fallback here is for the type checker, which cannot read SQL.
    total = await conn.fetchval(_TEAM_COST_SINCE, team_id, owner_principal, since)
    return total if total is not None else Decimal(0)


async def usage_by_agent(
    conn: Conn, *, owner_principal: str, run_id: int | None, team_id: int | None
) -> list[asyncpg.Record]:
    """The read specs/teams-usage exists for: which role cost what. A `GROUP BY` rather
    than arithmetic on the way in, which is what one-row-per-call bought."""
    return list(await conn.fetch(_USAGE_BY_AGENT, owner_principal, run_id, team_id))


async def usage_by_model(
    conn: Conn, *, owner_principal: str, run_id: int | None, team_id: int | None
) -> list[asyncpg.Record]:
    return list(await conn.fetch(_USAGE_BY_MODEL, owner_principal, run_id, team_id))


async def usage_total_cost(
    conn: Conn, *, owner_principal: str, run_id: int | None, team_id: int | None
) -> Decimal:
    total = await conn.fetchval(_USAGE_TOTAL, owner_principal, run_id, team_id)
    return total if total is not None else Decimal(0)


# --- trades (specs/teams-trading) -----------------------------------------------------

_INSERT_TRADE = """
    INSERT INTO trades (
        run_id, run_step_id, agent_key, tool_name, symbol, direction, size, level
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
    RETURNING id, run_id, run_step_id, agent_key, tool_name, symbol, direction, size,
              level, status, result_status, provider_order_id, reference, created_at,
              settled_at
"""

_SETTLE_TRADE = """
    UPDATE trades
       SET status = $2,
           result_status = $3,
           provider_order_id = $4,
           reference = $5,
           settled_at = now()
     WHERE id = $1
    RETURNING id, run_id, run_step_id, agent_key, tool_name, symbol, direction, size,
              level, status, result_status, provider_order_id, reference, created_at,
              settled_at
"""

_TEAM_TRADES_SINCE = """
    SELECT COUNT(*)::bigint AS placed
      FROM trades t
      JOIN runs r ON r.id = t.run_id
      JOIN team_revisions v ON v.id = r.team_revision_id
     WHERE v.team_id = $1 AND r.owner_principal = $2 AND t.created_at >= $3
"""

_RUN_TRADES = """
    SELECT id, run_id, run_step_id, agent_key, tool_name, symbol, direction, size, level,
           status, result_status, provider_order_id, reference, created_at, settled_at
      FROM trades
     WHERE run_id = $1
     ORDER BY id
"""


async def record_trade(
    conn: Conn,
    *,
    run_id: int,
    run_step_id: int,
    agent_key: str,
    tool_name: str,
    symbol: str | None,
    direction: str | None,
    size: Decimal | None,
    level: Decimal | None,
) -> asyncpg.Record:
    """Written **before** the call goes out, with `status` left at `sent`.

    The order matters and it is the whole reason this function is separate from
    `settle_trade`: a process that dies between the two leaves a row saying an order was
    sent and its fate unknown, which is true. Writing once, afterwards, would leave
    nothing at all — and "no row" reads as "no order", which is the one wrong answer
    (specs/teams-trading, "Wiersz MUST powstać przed wysłaniem wywołania").
    """
    return await fetch_one(
        conn,
        _INSERT_TRADE,
        run_id,
        run_step_id,
        agent_key,
        tool_name,
        symbol,
        direction,
        size,
        level,
    )


async def settle_trade(
    conn: Conn,
    *,
    trade_id: int,
    status: str,
    result_status: str | None,
    provider_order_id: str | None,
    reference: str | None,
) -> asyncpg.Record:
    """What came back, onto the row that was already there."""
    return await fetch_one(
        conn, _SETTLE_TRADE, trade_id, status, result_status, provider_order_id, reference
    )


async def team_trades_since(
    conn: Conn, *, team_id: int, owner_principal: str, since: datetime
) -> int:
    """How many orders this team has placed since a moment — the daily ceiling's own
    question (specs/teams-trading, "Granica dobowa jest sprawdzana przed utworzeniem
    przebiegu").

    Counts rows, not successes: an order whose result never came back was still placed,
    and a ceiling that forgave it would be a ceiling an outage could walk through.
    """
    placed = await conn.fetchval(_TEAM_TRADES_SINCE, team_id, owner_principal, since)
    return placed if placed is not None else 0


async def get_run_trades(conn: Conn, *, run_id: int) -> list[asyncpg.Record]:
    return list(await conn.fetch(_RUN_TRADES, run_id))


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


# --- schedules, triggers, and the fires either one produces ---------------------------
#
# `schedules.owner_principal` and `triggers.owner_principal` are copied at creation
# rather than reached through the team they point at — the same reasoning
# `runs.owner_principal` already carries in this file: an access check MUST NOT depend
# on a join, and a row survives its team being retired (specs/teams-schedules,
# "Harmonogram należy do operatora, który go zapisał").
#
# Every "claim" statement below is a conditional UPDATE whose WHERE clause is the whole
# of the exactly-once guarantee (design.md, "Wyzwolenie przejmowane w bazie, nie
# posiadane przez proces"): a second caller's UPDATE waits on Postgres's own row lock,
# then re-evaluates the same WHERE against the row the first caller already advanced —
# and finds it no longer due. No advisory lock, no "leader" process, nothing that
# outlives one statement.


class _Recurring:
    """The statements a schedule and a trigger hold in common, written once per table.

    The two tables are the same machine pointed at different questions — a clock or a
    condition — and everything that follows from being that machine is identical in both:
    who owns the row, whether it is enabled, how many times in a row it has failed, and
    the conditional UPDATE that claims its next turn. Only the table name, the column
    list and the name of the "due" column differ, and those are what this class carries.

    Written as one statement per rule rather than two copies of each because the rules
    are the load-bearing part and a copy only has to drift once: `set_enabled` decides
    what re-enabling clears, `delete` decides that "not yours" and "not there" are one
    answer, and `claim` is the whole of the exactly-once guarantee. Each of those was
    true twice and had to stay true twice.

    What is deliberately *not* here is what genuinely differs: the INSERT and UPDATE
    column lists, which have nothing in common beyond `team_id`, and
    `record_trigger_check`, which only one of the two has at all.
    """

    def __init__(self, *, table: str, columns: str, due_column: str, fire_column: str) -> None:
        self.select = f"""
            SELECT {columns} FROM {table} WHERE id = $1 AND owner_principal = $2
        """

        self.select_for_team = f"""
            SELECT {columns} FROM {table}
             WHERE team_id = $1 AND owner_principal = $2
             ORDER BY created_at DESC, id DESC
        """

        # Re-enabling clears whatever disabled it and gives it a clean run of failures —
        # the same "włączyć z powrotem" specs/teams-schedules describes. Disabling by an
        # operator's own choice leaves `disabled_reason` as it was (usually NULL): the
        # operator needs no explanation of a decision they just made themselves.
        self.set_enabled = f"""
            UPDATE {table}
               SET enabled = $3,
                   disabled_reason = CASE WHEN $3 THEN NULL ELSE disabled_reason END,
                   consecutive_failures = CASE WHEN $3 THEN 0 ELSE consecutive_failures END,
                   updated_at = now()
             WHERE id = $1 AND owner_principal = $2
            RETURNING {columns}
        """

        # The owner rides in the WHERE rather than being checked after the read, so "not
        # yours" and "not there" are one statement and one answer — a route that could
        # tell them apart would be telling a stranger that the row exists.
        self.delete = f"""
            DELETE FROM {table} WHERE id = $1 AND owner_principal = $2 RETURNING id
        """

        # System-initiated — no owner filter, because the caller is the clock loop acting
        # on a row it already resolved, not an operator's request (specs/teams-schedules,
        # "Harmonogram po serii nieudanych przebiegów wyłącza się sam").
        self.disable_for_failures = f"""
            UPDATE {table} SET enabled = false, disabled_reason = $2, updated_at = now()
             WHERE id = $1
            RETURNING {columns}
        """

        self.increment_failures = f"""
            UPDATE {table}
               SET consecutive_failures = consecutive_failures + 1, updated_at = now()
             WHERE id = $1
            RETURNING {columns}
        """

        self.reset_failures = f"""
            UPDATE {table} SET consecutive_failures = 0, updated_at = now()
             WHERE id = $1
            RETURNING {columns}
        """

        self.claim_due = f"""
            UPDATE {table} SET {due_column} = $2, updated_at = now()
             WHERE id = $1 AND enabled AND {due_column} <= now()
            RETURNING {columns}
        """

        # No owner filter — the clock (`scheduler/`) works across every operator's rows
        # at once, the one place in this module that legitimately does. `enabled` rides in
        # the WHERE rather than being filtered in Python so the partial index on
        # `({due_column}) WHERE enabled` is what answers this, not a table scan.
        self.select_due = f"""
            SELECT {columns} FROM {table} WHERE enabled AND {due_column} <= now()
        """

        self.select_fires = f"""
            SELECT f.id, f.schedule_id, f.trigger_id, f.fired_at, f.outcome, f.reason,
                   f.run_id, f.skipped_count
              FROM schedule_fires f
              JOIN {table} o ON o.id = f.{fire_column}
             WHERE f.{fire_column} = $1 AND o.owner_principal = $2
             ORDER BY f.fired_at DESC, f.id DESC
        """

        # `runs` carries no `schedule_id`/`trigger_id` (design.md, "Trzy nowe tabele, zero
        # zmian w tabelach fazy 1") — the fire that started a run is the only record of
        # which run belongs to which schedule or trigger, so "is the previous run of this
        # one still working" is answered by walking back to the most recent `started` fire
        # and reading the status of the run it names, not by a join `runs` could offer.
        self.latest_run_status = f"""
            SELECT r.status
              FROM schedule_fires f
              JOIN runs r ON r.id = f.run_id
             WHERE f.{fire_column} = $1 AND f.outcome = 'started'
             ORDER BY f.fired_at DESC
             LIMIT 1
        """


_SCHEDULE_COLUMNS = """
    id, team_id, owner_principal, revision_mode, pinned_revision_id, cron_expression,
    next_fire_at, enabled, disabled_reason, consecutive_failures,
    created_at, updated_at
"""

_TRIGGER_COLUMNS = """
    id, team_id, owner_principal, revision_mode, pinned_revision_id, tool_name,
    arguments, field_path, comparison, threshold, cooldown_seconds,
    poll_interval_seconds, next_check_at, last_result, last_checked_at, last_fired_at,
    enabled, disabled_reason, consecutive_failures, created_at, updated_at
"""

_SCHEDULES = _Recurring(
    table="schedules",
    columns=_SCHEDULE_COLUMNS,
    due_column="next_fire_at",
    fire_column="schedule_id",
)

_TRIGGERS = _Recurring(
    table="triggers",
    columns=_TRIGGER_COLUMNS,
    due_column="next_check_at",
    fire_column="trigger_id",
)


_INSERT_SCHEDULE = f"""
    INSERT INTO schedules (
        team_id, owner_principal, revision_mode, pinned_revision_id,
        cron_expression, next_fire_at
    )
    VALUES ($1, $2, $3, $4, $5, $6)
    RETURNING {_SCHEDULE_COLUMNS}
"""

_UPDATE_SCHEDULE = f"""
    UPDATE schedules
       SET revision_mode = $3, pinned_revision_id = $4, cron_expression = $5,
           next_fire_at = $6, updated_at = now()
     WHERE id = $1 AND owner_principal = $2
    RETURNING {_SCHEDULE_COLUMNS}
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
    return await conn.fetchrow(_SCHEDULES.select, schedule_id, owner_principal)


async def list_schedules_for_team(
    conn: Conn, *, team_id: int, owner_principal: str
) -> list[asyncpg.Record]:
    return list(await conn.fetch(_SCHEDULES.select_for_team, team_id, owner_principal))


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
    return await conn.fetchrow(_SCHEDULES.set_enabled, schedule_id, owner_principal, enabled)


async def delete_schedule(conn: Conn, *, schedule_id: int, owner_principal: str) -> bool:
    """Whether a row was deleted — `False` covers both "not there" and "not yours", which
    the owner filter inside the statement makes the same answer.

    The fire history goes with it, by `ON DELETE CASCADE` in migration `0007` rather than
    by a second statement here: the same rule written twice drifts the first time a caller
    forgets half of it. Runs are untouched — nothing in `runs` points at a schedule, it is
    the fire rows that point at runs (specs/teams-schedules, "Harmonogram i wyzwalacz dają
    się usunąć").
    """
    row = await conn.fetchrow(_SCHEDULES.delete, schedule_id, owner_principal)
    return row is not None


async def disable_schedule_for_failures(
    conn: Conn, *, schedule_id: int, reason: str
) -> asyncpg.Record | None:
    return await conn.fetchrow(_SCHEDULES.disable_for_failures, schedule_id, reason)


async def increment_schedule_failures(conn: Conn, *, schedule_id: int) -> asyncpg.Record | None:
    return await conn.fetchrow(_SCHEDULES.increment_failures, schedule_id)


async def reset_schedule_failures(conn: Conn, *, schedule_id: int) -> asyncpg.Record | None:
    return await conn.fetchrow(_SCHEDULES.reset_failures, schedule_id)


async def claim_due_schedule(
    conn: Conn, *, schedule_id: int, next_fire_at: datetime
) -> asyncpg.Record | None:
    """`None` means somebody else already claimed this fire, or it was disabled between
    being listed as due and this call — either way, this caller does nothing further."""
    return await conn.fetchrow(_SCHEDULES.claim_due, schedule_id, next_fire_at)


async def list_due_schedules(conn: Conn) -> list[asyncpg.Record]:
    """Every enabled schedule due right now, across every owner — what one wake of the
    clock works through before attempting to claim each (specs/teams-schedules)."""
    return list(await conn.fetch(_SCHEDULES.select_due))


_INSERT_TRIGGER = f"""
    INSERT INTO triggers (
        team_id, owner_principal, revision_mode, pinned_revision_id,
        tool_name, arguments, field_path, comparison, threshold,
        cooldown_seconds, poll_interval_seconds, next_check_at
    )
    VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, $10, $11, $12)
    RETURNING {_TRIGGER_COLUMNS}
"""

_UPDATE_TRIGGER = f"""
    UPDATE triggers
       SET revision_mode = $3, pinned_revision_id = $4, tool_name = $5,
           arguments = $6::jsonb, field_path = $7, comparison = $8, threshold = $9,
           cooldown_seconds = $10, poll_interval_seconds = $11,
           updated_at = now()
     WHERE id = $1 AND owner_principal = $2
    RETURNING {_TRIGGER_COLUMNS}
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
    RETURNING {_TRIGGER_COLUMNS}
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
    return await conn.fetchrow(_TRIGGERS.select, trigger_id, owner_principal)


async def list_triggers_for_team(
    conn: Conn, *, team_id: int, owner_principal: str
) -> list[asyncpg.Record]:
    return list(await conn.fetch(_TRIGGERS.select_for_team, team_id, owner_principal))


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
    return await conn.fetchrow(_TRIGGERS.set_enabled, trigger_id, owner_principal, enabled)


async def delete_trigger(conn: Conn, *, trigger_id: int, owner_principal: str) -> bool:
    """The same as `delete_schedule`, for the other half of the pair — including the fire
    history going with it and the runs staying."""
    row = await conn.fetchrow(_TRIGGERS.delete, trigger_id, owner_principal)
    return row is not None


async def disable_trigger_for_failures(
    conn: Conn, *, trigger_id: int, reason: str
) -> asyncpg.Record | None:
    return await conn.fetchrow(_TRIGGERS.disable_for_failures, trigger_id, reason)


async def increment_trigger_failures(conn: Conn, *, trigger_id: int) -> asyncpg.Record | None:
    return await conn.fetchrow(_TRIGGERS.increment_failures, trigger_id)


async def reset_trigger_failures(conn: Conn, *, trigger_id: int) -> asyncpg.Record | None:
    return await conn.fetchrow(_TRIGGERS.reset_failures, trigger_id)


async def claim_trigger_for_check(
    conn: Conn, *, trigger_id: int, next_check_at: datetime
) -> asyncpg.Record | None:
    """`None` means another process is already evaluating this trigger's next check, or
    it was disabled in between — mirrors `claim_due_schedule`."""
    return await conn.fetchrow(_TRIGGERS.claim_due, trigger_id, next_check_at)


async def list_due_triggers(conn: Conn) -> list[asyncpg.Record]:
    """Every enabled trigger due for a check right now, across every owner — mirrors
    `list_due_schedules`."""
    return list(await conn.fetch(_TRIGGERS.select_due))


async def record_trigger_check(
    conn: Conn, *, trigger_id: int, result: bool | None, fired: bool
) -> asyncpg.Record:
    return await fetch_one(conn, _RECORD_TRIGGER_CHECK, trigger_id, result, fired)


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
    return list(await conn.fetch(_SCHEDULES.select_fires, schedule_id, owner_principal))


async def list_fires_for_trigger(
    conn: Conn, *, trigger_id: int, owner_principal: str
) -> list[asyncpg.Record]:
    return list(await conn.fetch(_TRIGGERS.select_fires, trigger_id, owner_principal))


async def latest_run_status_for_schedule(conn: Conn, *, schedule_id: int) -> str | None:
    """`None` when this schedule has never started a run — never mistaken for "the run
    finished", which is a real status (`completed`) and not the absence of one."""
    return await conn.fetchval(_SCHEDULES.latest_run_status, schedule_id)


async def latest_run_status_for_trigger(conn: Conn, *, trigger_id: int) -> str | None:
    return await conn.fetchval(_TRIGGERS.latest_run_status, trigger_id)
