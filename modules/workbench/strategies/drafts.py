"""The agent's drafts: a document put into the operator's editor without a revision — one per strategy, and one for the
new strategy not saved yet (`strategy_id` None). Saving a revision is what ends a draft."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from tc_runtime.db import Conn, fetch_one

from .store import decoded

_PLACE = "coalesce(strategy_id, 0) = coalesce($1::bigint, 0)"


@dataclass(frozen=True)
class Draft:
    strategy_id: int | None
    document: dict[str, Any]
    seq: int
    updated_at: datetime


async def put(conn: Conn, strategy_id: int | None, document: dict[str, Any]) -> Draft:
    """Replaces the place's draft. A new `seq` every time, so the same document put twice is still news to the editor."""
    async with conn.transaction():
        await conn.execute(f"DELETE FROM strategy_drafts WHERE {_PLACE}", strategy_id)
        row = await fetch_one(
            conn,
            "INSERT INTO strategy_drafts (strategy_id, document) VALUES ($1, $2::jsonb) RETURNING *",
            strategy_id, json.dumps(document),
        )
    return Draft(row["strategy_id"], decoded(row["document"]), row["seq"], row["updated_at"])


async def get(conn: Conn, strategy_id: int | None) -> Draft | None:
    row = await conn.fetchrow(f"SELECT * FROM strategy_drafts WHERE {_PLACE}", strategy_id)
    return None if row is None else Draft(row["strategy_id"], decoded(row["document"]), row["seq"], row["updated_at"])


async def discard(conn: Conn, strategy_id: int | None) -> None:
    await conn.execute(f"DELETE FROM strategy_drafts WHERE {_PLACE}", strategy_id)
