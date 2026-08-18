"""What the agent set the terminal to draw, in the order it said it."""

from __future__ import annotations

import json
from collections.abc import Sequence

import asyncpg
from tc_runtime.db import Conn, fetch_one

from ..models import (
    ChartCommand,
    ChartFocus,
    ChartIndicator,
)

_INSERT_CHART_COMMAND = """
    INSERT INTO chart_commands (session_id, symbol, resolution, indicators, focus)
    VALUES ($1, $2, $3, $4, $5)
    RETURNING id AS sequence, session_id, symbol, resolution, indicators, focus, created_at
"""

_SELECT_CHART_COMMANDS_AFTER = """
    SELECT id AS sequence, session_id, symbol, resolution, indicators, focus, created_at
      FROM chart_commands
     WHERE id > $1
     ORDER BY id
"""


def _chart_command_from_row(row: asyncpg.Record) -> ChartCommand:
    data = dict(row)
    raw = data["indicators"]
    if isinstance(raw, str):
        raw = json.loads(raw)
    data["indicators"] = None if raw is None else [ChartIndicator(**item) for item in raw]
    raw_focus = data["focus"]
    if isinstance(raw_focus, str):
        raw_focus = json.loads(raw_focus)
    data["focus"] = None if raw_focus is None else ChartFocus(**raw_focus)
    return ChartCommand(**data)


async def record_chart_command(
    conn: Conn,
    *,
    session_id: int,
    symbol: str | None,
    resolution: str | None,
    indicators: Sequence[ChartIndicator] | None,
    focus: ChartFocus | None,
) -> ChartCommand:
    """One row per accepted command, never an update of the previous one. The id it comes
    back with is the sequence a consumer remembers having applied."""
    payload = (
        None
        if indicators is None
        else json.dumps([indicator.model_dump() for indicator in indicators])
    )
    focus_payload = None if focus is None else focus.model_dump_json()
    row = await fetch_one(
        conn, _INSERT_CHART_COMMAND, session_id, symbol, resolution, payload, focus_payload
    )
    return _chart_command_from_row(row)


async def chart_state_after(conn: Conn, *, sequence: int) -> ChartCommand | None:
    """Every command newer than `sequence`, folded into one — or `None` when there is
    none.

    Folded rather than returned as a list because the consumer only needs to know what the
    chart should look like now; and folded rather than "just the newest" because a command
    that set only the indicators and a later one that set only the symbol each say
    something the other does not (`ChartCommand.merged_with`).

    Unbounded on purpose: this table grows at the speed of an operator asking for things,
    and a cap here would silently drop exactly the older command the fold exists to keep.
    """
    rows = await conn.fetch(_SELECT_CHART_COMMANDS_AFTER, sequence)
    folded: ChartCommand | None = None
    for row in rows:
        command = _chart_command_from_row(row)
        folded = command if folded is None else folded.merged_with(command)
    return folded
