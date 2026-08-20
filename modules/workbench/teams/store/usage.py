"""What a run cost — computed once, on the way in, and only ever summed afterwards.

The write sits beside the reads because one property binds them: `record_usage` is the
single place a cost is ever computed, and every read here sums `cost` as it was written.
Nothing recomputes from tokens and rates — a cennik changed after a run MUST NOT reprice it
(specs/teams-usage, "Koszt jest przypisany do wiersza w chwili zapisu"), and a SUM over a
column is the only shape that cannot accidentally do otherwise.

`owner_principal` rides on `runs`, so every read is owner-scoped without a join through the
catalogue — and a retired team's runs still answer.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import asyncpg
from tc_runtime.db import Conn, fetch_one

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
