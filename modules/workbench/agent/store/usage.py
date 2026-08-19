"""What each turn cost, written once and read back two ways.

The write and the aggregates were 250 lines apart in the single-file store, with the
whole tool-call section wedged between them. They are one table and one subject.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import asyncpg
from tc_runtime.db import Conn, fetch_one

from ..models import (
    Usage,
    UsageAggregate,
)

_INSERT_USAGE = """
    INSERT INTO usage (
        session_id, message_id, model_id,
        input_tokens, output_tokens, cached_tokens, reasoning_tokens,
        input_rate_per_1m, output_rate_per_1m, cost
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
    RETURNING id, session_id, message_id, model_id,
              input_tokens, output_tokens, cached_tokens, reasoning_tokens,
              input_rate_per_1m, output_rate_per_1m, cost, created_at
"""

def _usage_from_row(row: asyncpg.Record) -> Usage:
    return Usage(**dict(row))

async def record_usage(
    conn: Conn,
    *,
    session_id: int,
    message_id: int,
    model_id: str,
    input_tokens: int | None,
    output_tokens: int | None,
    cached_tokens: int | None,
    reasoning_tokens: int | None,
    input_rate_per_1m: Decimal,
    output_rate_per_1m: Decimal,
) -> Usage:
    """The one place a cost is computed, and the only moment it ever is — never again at
    read time (specs/agent-usage, "Koszt jest przypisany do wiersza w chwili zapisu")."""
    cost = None
    if input_tokens is not None and output_tokens is not None:
        cost = (Decimal(input_tokens) / 1_000_000 * input_rate_per_1m) + (
            Decimal(output_tokens) / 1_000_000 * output_rate_per_1m
        )
    row = await fetch_one(
        conn,
        _INSERT_USAGE,
        session_id,
        message_id,
        model_id,
        input_tokens,
        output_tokens,
        cached_tokens,
        reasoning_tokens,
        input_rate_per_1m,
        output_rate_per_1m,
        cost,
    )
    return _usage_from_row(row)


# Every aggregate is scoped to the caller's own sessions (the `JOIN sessions` filters on
# `owner_principal`) — usage belongs to whoever the session belongs to, same as the
# transcript does. `SUM` ignores NULL rows on its own; `unknown_count` is what a caller
# would otherwise never learn it silently dropped.

_AGGREGATE_COLUMNS = """
    COALESCE(SUM(u.input_tokens), 0)::bigint AS input_tokens,
    COALESCE(SUM(u.output_tokens), 0)::bigint AS output_tokens,
    COALESCE(SUM(u.cost), 0) AS cost,
    COUNT(*) FILTER (WHERE u.cost IS NULL)::bigint AS unknown_count
"""

_AGGREGATE_WHERE = """
    WHERE s.owner_principal = $1
      AND ($2::timestamptz IS NULL OR u.created_at >= $2)
      AND ($3::timestamptz IS NULL OR u.created_at < $3)
"""

_USAGE_BY_MODEL = f"""
    SELECT u.model_id AS key, {_AGGREGATE_COLUMNS}
      FROM usage u JOIN sessions s ON s.id = u.session_id
    {_AGGREGATE_WHERE}
     GROUP BY u.model_id
     ORDER BY u.model_id
"""

_USAGE_BY_SESSION = f"""
    SELECT u.session_id::text AS key, {_AGGREGATE_COLUMNS}
      FROM usage u JOIN sessions s ON s.id = u.session_id
    {_AGGREGATE_WHERE}
     GROUP BY u.session_id
     ORDER BY u.session_id
"""

_USAGE_BY_DAY = f"""
    SELECT to_char(date_trunc('day', u.created_at), 'YYYY-MM-DD') AS key, {_AGGREGATE_COLUMNS}
      FROM usage u JOIN sessions s ON s.id = u.session_id
    {_AGGREGATE_WHERE}
     GROUP BY 1
     ORDER BY 1
"""

_USAGE_TOTAL_COST = f"""
    SELECT COALESCE(SUM(u.cost), 0) AS total_cost
      FROM usage u JOIN sessions s ON s.id = u.session_id
    {_AGGREGATE_WHERE}
"""


def _aggregate_from_row(row: asyncpg.Record) -> UsageAggregate:
    return UsageAggregate(**dict(row))


async def usage_by_model(
    conn: Conn, *, owner_principal: str, since: datetime | None, until: datetime | None
) -> list[UsageAggregate]:
    rows = await conn.fetch(_USAGE_BY_MODEL, owner_principal, since, until)
    return [_aggregate_from_row(row) for row in rows]


async def usage_by_session(
    conn: Conn, *, owner_principal: str, since: datetime | None, until: datetime | None
) -> list[UsageAggregate]:
    rows = await conn.fetch(_USAGE_BY_SESSION, owner_principal, since, until)
    return [_aggregate_from_row(row) for row in rows]


async def usage_by_day(
    conn: Conn, *, owner_principal: str, since: datetime | None, until: datetime | None
) -> list[UsageAggregate]:
    rows = await conn.fetch(_USAGE_BY_DAY, owner_principal, since, until)
    return [_aggregate_from_row(row) for row in rows]


async def usage_total_cost(
    conn: Conn, *, owner_principal: str, since: datetime | None, until: datetime | None
) -> Decimal:
    row = await fetch_one(conn, _USAGE_TOTAL_COST, owner_principal, since, until)
    return row["total_cost"]
