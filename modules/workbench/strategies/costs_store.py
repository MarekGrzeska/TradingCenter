"""The cost profile the operator sets for an instrument: what a run from the conversation costs, and what the run form
starts from. A run copies the values it used into its `request`, so replacing a profile never moves a recorded result."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from tc_runtime.db import Conn

from .costs import CostModel
from .store import decoded


@dataclass(frozen=True)
class Profile:
    symbol: str
    costs: CostModel
    updated_at: datetime


def _profile(row) -> Profile:
    return Profile(row["symbol"], CostModel.model_validate(decoded(row["costs"])), row["updated_at"])


async def get(conn: Conn, symbol: str) -> Profile | None:
    row = await conn.fetchrow("SELECT * FROM cost_profiles WHERE symbol = $1", symbol)
    return None if row is None else _profile(row)


async def list_all(conn: Conn) -> list[Profile]:
    return [_profile(row) for row in await conn.fetch("SELECT * FROM cost_profiles ORDER BY symbol")]


async def put(conn: Conn, symbol: str, costs: CostModel) -> Profile:
    row = await conn.fetchrow(
        "INSERT INTO cost_profiles (symbol, costs) VALUES ($1, $2::jsonb) "
        "ON CONFLICT (symbol) DO UPDATE SET costs = EXCLUDED.costs, updated_at = now() RETURNING *",
        symbol, json.dumps(costs.model_dump(mode="json")),
    )
    return _profile(row)
