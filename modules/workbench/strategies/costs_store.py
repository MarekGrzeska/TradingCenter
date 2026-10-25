"""The cost profile of each instrument: read off the broker the first time a run needs one, then kept until the operator
changes it or asks the broker again (design D2). A run copies the values it used into its `request`, so replacing a
profile never moves a recorded result."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from tc_runtime.db import Conn

from . import broker_costs
from .archive import Archive
from .costs import CostModel
from .store import decoded

Source = Literal["operator", "broker"]


@dataclass(frozen=True)
class Profile:
    symbol: str
    costs: CostModel
    updated_at: datetime
    source: Source
    fetched_at: datetime | None
    broker: dict[str, Any] | None


def _profile(row) -> Profile:
    return Profile(
        row["symbol"], CostModel.model_validate(decoded(row["costs"])), row["updated_at"], row["source"],
        row["fetched_at"], decoded(row["broker"]),
    )


async def get(conn: Conn, symbol: str) -> Profile | None:
    row = await conn.fetchrow("SELECT * FROM cost_profiles WHERE symbol = $1", symbol)
    return None if row is None else _profile(row)


async def list_all(conn: Conn) -> list[Profile]:
    return [_profile(row) for row in await conn.fetch("SELECT * FROM cost_profiles ORDER BY symbol")]


async def put(conn: Conn, symbol: str, costs: CostModel) -> Profile:
    """The operator's values. What the broker said no longer describes them, so it is not kept."""
    row = await conn.fetchrow(
        "INSERT INTO cost_profiles (symbol, costs) VALUES ($1, $2::jsonb) "
        "ON CONFLICT (symbol) DO UPDATE SET costs = EXCLUDED.costs, updated_at = now(), source = 'operator', "
        "fetched_at = NULL, broker = NULL RETURNING *",
        symbol, json.dumps(costs.model_dump(mode="json")),
    )
    return _profile(row)


async def put_from_broker(conn: Conn, symbol: str, read: broker_costs.BrokerCosts, *, replace: bool = True) -> Profile:
    """`replace=False` keeps a profile written meanwhile — two first runs at once fetch twice and keep the first."""
    on_conflict = (
        "DO UPDATE SET costs = EXCLUDED.costs, updated_at = now(), source = 'broker', fetched_at = now(), "
        "broker = EXCLUDED.broker" if replace else "DO NOTHING"
    )
    await conn.execute(
        "INSERT INTO cost_profiles (symbol, costs, source, fetched_at, broker) VALUES ($1, $2::jsonb, 'broker', now(), "
        f"$3::jsonb) ON CONFLICT (symbol) {on_conflict}",
        symbol, json.dumps(read.costs.model_dump(mode="json")), json.dumps(read.raw),
    )
    found = await get(conn, symbol)
    assert found is not None
    return found


async def get_or_fetch(conn: Conn, archive: Archive, symbol: str) -> Profile:
    """The instrument's profile, read off the broker and kept when there is none. Raises what `broker_costs.fetch`
    raises, having written nothing."""
    found = await get(conn, symbol)
    if found is not None:
        return found
    return await put_from_broker(conn, symbol, await broker_costs.fetch(archive, symbol), replace=False)
