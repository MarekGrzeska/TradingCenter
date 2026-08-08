"""Turning "these pairs, from this moment" into chunks — and pricing that without
running it.

Nothing here talks to the gateway. Planning only ever reads what the archive already
knows about a pair — its coverage and its provider boundary — so a plan and its price
come from exactly the same arithmetic the runner will later execute. That equality is
the whole point: what a dialog shows an operator is what will happen, not a second
guess computed a different way.
"""

from __future__ import annotations

import math
from datetime import datetime

import asyncpg
from pydantic import BaseModel

from ..coverage import earliest_reachable, uncovered_within
from ..ingest.backfill import MAX_BARS_PER_FILL
from ..models import Resolution
from ..periods import period_length
from .models import ChunkPlan


class FutureRequest(Exception):
    """A moment later than now was asked for. There is no history there to reach for."""


def periods_between(resolution: Resolution, start: datetime, end: datetime) -> int:
    """How many candles of this resolution fit in `[start, end)`, rounded up.

    Calendar periods, not a session calendar — a market shut for part of the window
    yields fewer candles than this, never more, so the count this produces is a safe
    overestimate rather than a guess that could come in short.
    """
    if end <= start:
        return 0
    seconds = (end - start).total_seconds()
    return math.ceil(seconds / period_length(resolution).total_seconds())


def split_into_windows(
    resolution: Resolution, start: datetime, end: datetime
) -> list[tuple[datetime, datetime]]:
    """One gap, cut into windows no wider than `MAX_BARS_PER_FILL` candles each.

    **Newest window first.** Each window becomes one chunk and one gateway request —
    `before=window_end`, reaching back for the candles the window holds — so a window
    wider than the gateway's own ceiling would be a chunk that request can never satisfy.

    The order is load-bearing, not cosmetic. `earliest_reachable` may still be unknown
    when a deep request is planned — an operator asking for "everything" clips only to
    what coverage already knows, and a pair's true depth is not among that yet. Planned
    oldest-first, the runner would spend one gateway request per chunk marching back
    from a boundary nobody has found, discovering the same "nothing here" answer
    hundreds of times before reaching data. Newest-first, the chunk that actually finds
    the boundary runs early, and every chunk still queued behind it — by definition
    older, by definition past that boundary — is skipped in bulk rather than individually
    rediscovering it (`jobs/store.py`, `skip_chunks_beyond_history`).
    """
    if end <= start:
        return []
    width = period_length(resolution) * MAX_BARS_PER_FILL
    windows: list[tuple[datetime, datetime]] = []
    cursor = end
    while cursor > start:
        window_start = max(cursor - width, start)
        windows.append((window_start, cursor))
        cursor = window_start
    return windows


async def plan_chunks(
    conn: asyncpg.Connection,
    symbol: str,
    resolution: Resolution,
    requested_from: datetime,
    now: datetime,
) -> tuple[list[ChunkPlan], datetime]:
    """Chunks for one pair, and the moment `requested_from` was actually clipped to.

    Clipped to the provider's own boundary when it is known (`earliest_reachable`), and
    to what the archive has not already verified (`uncovered_within`) — a pair that
    already covers the whole requested range plans zero chunks, not a chunk asking the
    provider to confirm what is already known.

    Raises `FutureRequest` for a moment later than `now`; never raises for a moment
    earlier than the provider's own history, which is clipped rather than refused
    (design.md, "Data OD jest przycinana, nigdy odrzucana").
    """
    if requested_from > now:
        raise FutureRequest(
            f"{requested_from.isoformat()} is in the future; there is no history there"
        )

    reachable = await earliest_reachable(conn, symbol, resolution)
    effective_from = max(requested_from, reachable) if reachable is not None else requested_from

    gaps = await uncovered_within(conn, symbol, resolution, effective_from, now)

    # `uncovered_within` returns gaps oldest first; reversed here so the whole pair's
    # chunks run newest-first end to end, not just within one gap — see
    # `split_into_windows` for why the order matters.
    plans = [
        ChunkPlan(symbol=symbol, resolution=resolution, chunk_start=window_start, chunk_end=window_end)
        for gap_start, gap_end in reversed(gaps)
        for window_start, window_end in split_into_windows(resolution, gap_start, gap_end)
    ]
    return plans, effective_from


class PairEstimate(BaseModel):
    """What one pair will cost, before anything is fetched."""

    symbol: str
    resolution: Resolution
    effective_from: datetime
    # True when `effective_from` differs from what was asked for — the provider's
    # history, or what the archive already holds, fell short of the request.
    clipped: bool
    estimated_candles: int
    estimated_bytes: int
    chunk_count: int


class JobEstimate(BaseModel):
    pairs: list[PairEstimate]
    total_estimated_candles: int
    total_estimated_bytes: int


# A rough, deliberately round figure for one stored candle: eight numeric columns plus
# per-row overhead. Never exact — session calendars are not consulted here — and the
# estimate says so; see `terminal-data-manager` spec, "Zatwierdzenie kreatora otwiera
# dialog akceptacji".
ESTIMATED_BYTES_PER_CANDLE = 96


async def estimate_job(
    conn: asyncpg.Connection,
    pairs: list[tuple[str, Resolution]],
    requested_from: datetime,
    now: datetime,
) -> JobEstimate:
    """Price a job for every pair, without creating it or touching what is tracked."""
    pair_estimates: list[PairEstimate] = []
    for symbol, resolution in pairs:
        chunks, effective_from = await plan_chunks(conn, symbol, resolution, requested_from, now)
        candles = sum(periods_between(resolution, c.chunk_start, c.chunk_end) for c in chunks)
        pair_estimates.append(
            PairEstimate(
                symbol=symbol,
                resolution=resolution,
                effective_from=effective_from,
                clipped=effective_from > requested_from,
                estimated_candles=candles,
                estimated_bytes=candles * ESTIMATED_BYTES_PER_CANDLE,
                chunk_count=len(chunks),
            )
        )
    return JobEstimate(
        pairs=pair_estimates,
        total_estimated_candles=sum(p.estimated_candles for p in pair_estimates),
        total_estimated_bytes=sum(p.estimated_bytes for p in pair_estimates),
    )
