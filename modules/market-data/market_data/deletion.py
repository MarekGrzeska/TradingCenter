"""Skasowanie — the operator's explicit, irreversible decision to remove a pair's data. Two steps:
`close_for_deletion` stops new work, then `delete_pair_data` removes candles and coverage together."""

from __future__ import annotations

from datetime import datetime

import asyncpg
from pydantic import BaseModel

from .coverage import delete_all_coverage
from .db import fetch_one
from .jobs.store import skip_pending_chunks_for_pair
from .models import Resolution
from .rollups import delete_all_for_symbol
from .store import delete_all_candles
from .tracking import TrackedPair, untrack


class PairDeletion(BaseModel):
    """A trace of one skasowanie — what it removed, kept after the data itself is gone."""

    symbol: str
    resolution: Resolution
    deleted_at: datetime
    candles_removed: int
    # Both null together, when the pair had never collected anything.
    removed_from: datetime | None
    removed_to: datetime | None


_INSERT_DELETION = """
    INSERT INTO pair_deletions (symbol, resolution, candles_removed, removed_from, removed_to)
    VALUES ($1, $2, $3, $4, $5)
    RETURNING deleted_at
"""

_SELECT_DELETIONS = """
    SELECT symbol, resolution, deleted_at, candles_removed, removed_from, removed_to
      FROM pair_deletions
     WHERE ($1::text IS NULL OR symbol = $1)
       AND ($2::text IS NULL OR resolution = $2)
     ORDER BY deleted_at DESC
"""


async def close_for_deletion(
    conn: asyncpg.Connection, symbol: str, resolution: Resolution
) -> TrackedPair | None:
    """Stop new work for a pair about to be deleted, as one transaction. Returns `None` if the pair
    was not tracked, which the caller reads as a refusal."""
    async with conn.transaction():
        stopped = await untrack(conn, symbol, resolution)
        if stopped is not None:
            await skip_pending_chunks_for_pair(conn, symbol, resolution)
    return stopped


async def delete_pair_data(
    conn: asyncpg.Connection, symbol: str, resolution: Resolution
) -> PairDeletion:
    """Remove a pair's candles and coverage, and record it — one transaction, so there is no moment
    where one exists without the other. Must run after `close_for_deletion` and an ingest sync."""
    async with conn.transaction():
        removed, earliest, latest = await delete_all_candles(conn, symbol, resolution)
        await delete_all_coverage(conn, symbol, resolution)
        if resolution is Resolution.MINUTE:
            await delete_all_for_symbol(conn, symbol)
        row = await fetch_one(
            conn, _INSERT_DELETION, symbol, resolution.value, removed, earliest, latest
        )

    return PairDeletion(
        symbol=symbol,
        resolution=resolution,
        deleted_at=row["deleted_at"],
        candles_removed=removed,
        removed_from=earliest,
        removed_to=latest,
    )


async def read_deletions(
    conn: asyncpg.Connection,
    symbol: str | None = None,
    resolution: Resolution | None = None,
) -> list[PairDeletion]:
    """Every recorded skasowanie, newest first, optionally narrowed to one pair — the same shape
    `jobs.list_jobs` takes, since the terminal reads both to build one instrument's history."""
    rows = await conn.fetch(_SELECT_DELETIONS, symbol, resolution.value if resolution else None)
    return [
        PairDeletion(
            symbol=row["symbol"],
            resolution=Resolution(row["resolution"]),
            deleted_at=row["deleted_at"],
            candles_removed=row["candles_removed"],
            removed_from=row["removed_from"],
            removed_to=row["removed_to"],
        )
        for row in rows
    ]
