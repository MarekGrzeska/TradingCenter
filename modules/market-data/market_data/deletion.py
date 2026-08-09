"""Skasowanie — the operator's explicit, irreversible decision to remove a pair's data.

Untracking a pair was never enough to answer "get rid of what this collected": it only
flips `tracked_pairs` and leaves candles and coverage in place, on purpose — that is
still what `tracking.untrack` does, and it is still correct for the fixed threshold of
"nothing kasuje itself". What was missing was a way to *ask* for the data to go, and
without one an operator who re-tracked a pair with a shorter range kept seeing the old
range back, because the old data was still there and its coverage told planning the
range was already fetched.

Deletion is that missing door, and it is deliberately two steps rather than one:

1. `close_for_deletion` stops anything new from starting on this pair — flips it
   untracked and skips its queued chunks — as one transaction. The caller then syncs
   ingest, which is how the live subscription actually stops; that is not a database
   operation and cannot live inside this module's transaction.
2. `delete_pair_data` removes the candles, the coverage, and (when the deleted series is
   the minute one) the rollups built from it, and records that it happened. One
   transaction, because a pair left with candles gone but coverage intact would look to
   planning like a pair already fully collected, and never be fetched again
   (`market-data-store` spec, "Skasowanie danych pary zdejmuje też jej pokrycie").

Nothing here calls the other from inside a transaction of its own — a chunk still in
flight when step 1 commits can finish afterwards, and `jobs.runner.execute_chunk` is
what refuses to write for a pair that is no longer tracked, closing that race rather than
this module trying to.
"""

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
    """Stop new work for a pair about to be deleted, as one transaction.

    Flips the pair untracked and settles its still-pending chunks as skipped, so nothing
    claims fresh work for a pair whose data is about to disappear. Returns `None` if the
    pair was not being tracked — meaning there is nothing to delete, which the caller
    reads as a refusal (`market-data-api` spec, "Skasowanie pary, która nie jest
    śledzona").
    """
    async with conn.transaction():
        stopped = await untrack(conn, symbol, resolution)
        if stopped is not None:
            await skip_pending_chunks_for_pair(conn, symbol, resolution)
    return stopped


async def delete_pair_data(
    conn: asyncpg.Connection, symbol: str, resolution: Resolution
) -> PairDeletion:
    """Remove a pair's candles and coverage, and record that it happened — one
    transaction, so there is no moment where one exists without the other.

    Must run after `close_for_deletion` has already stopped new work for this pair and
    the caller has synced ingest; neither is checked here, because both are the caller's
    to sequence (`app.py`'s `DELETE /pairs/{symbol}`).
    """
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
    """Every recorded skasowanie, newest first — optionally narrowed to one pair, the
    same shape `jobs.list_jobs` is narrowed by, since the terminal reads both to build
    one instrument's history."""
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
