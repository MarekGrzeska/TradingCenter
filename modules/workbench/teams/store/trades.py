"""Orders a run placed, and what came back (specs/teams-trading).

Two statements per order rather than one, and the order between them is the whole of it —
see `record_trade`.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import asyncpg
from tc_runtime.db import Conn, fetch_one

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
