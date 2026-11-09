"""Orders a run placed, and what came back. Two statements per order rather than one, and the order between
them is the whole of it — see `record_trade`."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import asyncpg
from tc_runtime.db import Conn, fetch_one

_INSERT_TRADE = """
    INSERT INTO trades (
        run_id, run_step_id, agent_key, tool_name, symbol, direction, size, level, account_id,
        environment, attempt_key
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
    RETURNING id, run_id, run_step_id, agent_key, tool_name, account_id, environment, symbol, direction, size,
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
    RETURNING id, run_id, run_step_id, agent_key, tool_name, account_id, environment, symbol, direction, size,
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

# The orders this team placed on a symbol that the provider took, newest first — what a step reads to tell its own
# position from anybody else's. A team's trades are a few a day; the join walks `runs` by its primary key.
_TEAM_PLACED_ORDERS = """
    SELECT t.id, t.agent_key, t.direction, t.size, t.level, t.provider_order_id, t.reference, t.created_at
      FROM trades t
      JOIN runs r ON r.id = t.run_id
      JOIN team_revisions v ON v.id = r.team_revision_id
     WHERE v.team_id = $1 AND r.owner_principal = $2 AND t.tool_name = 'place_order' AND t.symbol = $3
       AND t.status IN ('settled', 'unsettled')
     ORDER BY t.id DESC
     LIMIT $4
"""

_RUN_TRADES = """
    SELECT id, run_id, run_step_id, agent_key, tool_name, account_id, environment, symbol, direction,
           size, level,
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
    account_id: str | None = None,
    environment: str = "demo",
    symbol: str | None,
    direction: str | None,
    size: Decimal | None,
    level: Decimal | None,
    attempt_key: str | None = None,
) -> asyncpg.Record:
    """Written *before* the call goes out, with `status` left at `sent`. A process that dies between the two
    leaves a row saying an order was sent and its fate unknown, which is true — where no row reads as no order.
    Raises `AttemptAlreadyMade` when `attempt_key` was used before, and then nothing is written."""
    try:
        return await _insert_trade(
            conn, run_id, run_step_id, agent_key, tool_name, symbol, direction, size, level, account_id,
            environment, attempt_key,
        )
    except asyncpg.UniqueViolationError as err:
        raise AttemptAlreadyMade(attempt_key) from err


async def _insert_trade(conn: Conn, *values: object) -> asyncpg.Record:
    return await fetch_one(
        conn,
        _INSERT_TRADE,
        *values,
    )


class AttemptAlreadyMade(Exception):
    """The attempt this key names was made before, by this run or another: the call must not go out again."""

    def __init__(self, attempt_key: str | None) -> None:
        super().__init__(f"attempt {attempt_key} was already made")
        self.attempt_key = attempt_key


async def team_placed_orders(
    conn: Conn, *, team_id: int, owner_principal: str, symbol: str, limit: int = 20
) -> list[asyncpg.Record]:
    return list(await conn.fetch(_TEAM_PLACED_ORDERS, team_id, owner_principal, symbol, limit))


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
    """How many orders this team has placed since a moment — the daily ceiling's own question. Counts rows,
    not successes: an order whose result never came back was still placed."""
    placed = await conn.fetchval(_TEAM_TRADES_SINCE, team_id, owner_principal, since)
    return placed if placed is not None else 0


async def get_run_trades(conn: Conn, *, run_id: int) -> list[asyncpg.Record]:
    return list(await conn.fetch(_RUN_TRADES, run_id))
