"""The deposit each instrument requires, as a fraction of a position's value: read off the broker the first time a run
sized by it needs one, then kept until the operator changes it — never refreshed by a run, so two runs compare. A run
copies the value it used into its `request`."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from tc_runtime.db import Conn

from . import broker_costs
from .archive import Archive
from .store import decoded


@dataclass(frozen=True)
class Margin:
    symbol: str
    margin_factor: float
    source: Literal["broker", "operator"]
    broker: dict[str, Any] | None
    updated_at: datetime


def _margin(row) -> Margin:
    return Margin(row["symbol"], row["margin_factor"], row["source"], decoded(row["broker"]), row["updated_at"])


async def get(conn: Conn, symbol: str) -> Margin | None:
    row = await conn.fetchrow("SELECT * FROM instrument_margins WHERE symbol = $1", symbol)
    return None if row is None else _margin(row)


async def put(conn: Conn, symbol: str, margin_factor: float) -> Margin:
    row = await conn.fetchrow(
        "INSERT INTO instrument_margins (symbol, margin_factor, source) VALUES ($1, $2, 'operator') "
        "ON CONFLICT (symbol) DO UPDATE SET margin_factor = EXCLUDED.margin_factor, source = 'operator', broker = NULL, "
        "updated_at = now() RETURNING *",
        symbol, margin_factor,
    )
    return _margin(row)


async def get_or_fetch(conn: Conn, archive: Archive, symbol: str) -> Margin:
    """Raises what `broker_costs.fetch_margin` raises, having written nothing. Two first runs at once keep the first."""
    found = await get(conn, symbol)
    if found is not None:
        return found
    read = await broker_costs.fetch_margin(archive, symbol)
    await conn.execute(
        "INSERT INTO instrument_margins (symbol, margin_factor, source, broker) VALUES ($1, $2, 'broker', $3::jsonb) "
        "ON CONFLICT (symbol) DO NOTHING",
        symbol, read.margin_factor, json.dumps(read.raw),
    )
    stored = await get(conn, symbol)
    assert stored is not None
    return stored
