"""Turning "these pairs, from this moment" into chunks, and pricing that without running it. Nothing
here talks to the gateway: a plan and its price come from the arithmetic the runner will execute."""

from __future__ import annotations

from datetime import datetime

import asyncpg
from pydantic import BaseModel

from ..coverage import uncovered_within
from ..ingest.backfill import MAX_BARS_PER_FILL
from ..models import ESTIMATED_BYTES_PER_CANDLE, Resolution
from ..periods import period_length, periods_between
from .models import ChunkPlan


class FutureRequest(Exception):
    """A moment later than now was asked for. There is no history there to reach for."""


def split_into_windows(
    resolution: Resolution, start: datetime, end: datetime
) -> list[tuple[datetime, datetime]]:
    """One gap, cut into windows no wider than `MAX_BARS_PER_FILL` candles each, newest first. The
    order is load-bearing: the chunk that finds the provider's boundary runs early, and the rest skip."""
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
    """Chunks for one pair, and the moment `requested_from` was actually planned from. Not clipped to
    a recorded `history_ended`: that clip bit the one request meaning "check again", and bit silently."""
    if requested_from > now:
        raise FutureRequest(
            f"{requested_from.isoformat()} is in the future; there is no history there"
        )

    effective_from = requested_from
    gaps = await uncovered_within(conn, symbol, resolution, effective_from, now)

    # `uncovered_within` returns gaps oldest first; reversed so the whole pair's chunks run
    # newest-first end to end, not just within one gap.
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
    # True when `effective_from` differs from what was asked for. Nothing sets it today; kept because
    # the terminal renders it and the fact is real, just not known until the job has run.
    clipped: bool
    estimated_candles: int
    estimated_bytes: int
    chunk_count: int


class JobEstimate(BaseModel):
    pairs: list[PairEstimate]
    total_estimated_candles: int
    total_estimated_bytes: int


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
