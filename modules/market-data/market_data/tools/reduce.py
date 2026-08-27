"""Turning "more than the ceiling" into "the ceiling, and a note about it" — the one place a tool's
aggregation and truncation happens, so nothing disappears quietly."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Aggregation:
    original_count: int
    bucket_span: int


def aggregate_candles(
    candles: list[dict], target_count: int
) -> tuple[list[dict], Aggregation | None]:
    """Buckets `candles` down to roughly `target_count` entries, OHLC-merged, and a no-op when the series already
    fits: aggregating one that did not need it would answer a request for detail with less than was asked for."""
    n = len(candles)
    if n <= target_count or target_count <= 0:
        return candles, None

    bucket_span = math.ceil(n / target_count)
    buckets = [_merge_candles(candles[i : i + bucket_span]) for i in range(0, n, bucket_span)]
    return buckets, Aggregation(original_count=n, bucket_span=bucket_span)


def _merge_candles(chunk: list[dict]) -> dict:
    def field(name: str, reducer):
        values = [c[name] for c in chunk if c.get(name) is not None]
        return reducer(values) if values else None

    return {
        "time": chunk[0]["time"],
        "open": field("open", lambda vs: vs[0]),
        "high": field("high", max),
        "low": field("low", min),
        "close": field("close", lambda vs: vs[-1]),
    }


def truncate(items: list, limit: int) -> tuple[list, int]:
    """The first `limit` items, and how many were dropped."""
    if len(items) <= limit:
        return items, 0
    return items[:limit], len(items) - limit


def thin_series(values: list, target_count: int) -> tuple[list, int | None]:
    """Every `stride`-th value, keeping the series' shape recognizable instead of its every point — for a
    full-resolution series, not the OHLC series `aggregate_candles` merges. `None` when it already fits."""
    n = len(values)
    if n <= target_count or target_count <= 0:
        return values, None
    stride = math.ceil(n / target_count)
    return values[::stride], stride


# `cap_by_freshness` stood here until the tools moved in. It indexed its items as dicts, which stopped
# being true when they arrived as models, and it had no test to say so.
