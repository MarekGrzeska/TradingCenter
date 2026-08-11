"""A regression guard, not a benchmark.

The number that actually decided `routers/indicators.py`'s `REQUEST_CEILING` came from
running this same batch by hand and reading `time.perf_counter` across 200 repetitions
(design.md, "Sufit żądania zamiast odciążania wątkiem") — 5000 candles × 10 indicators
cost 16.5ms at p95 on the machine that measured it. This test is not that measurement: CI
hardware varies too much for a tight bound to mean anything. It exists to catch the
mistake that would invalidate the ceiling entirely — a vectorised primitive turning back
into an O(n²) one — with a bound generous enough to survive a slow runner.
"""

from __future__ import annotations

import time

import numpy as np

from market_data.indicators import kernel

# Ten times the measured p95, so only a real regression — not machine noise — trips it.
GENEROUS_BOUND_SECONDS = 0.165


def test_ten_indicators_on_five_thousand_candles_stays_fast():
    rng = np.random.default_rng(42)
    n = 5600
    close = 100 + np.cumsum(rng.normal(0, 0.5, n))
    high = close + rng.uniform(0, 1, n)
    low = close - rng.uniform(0, 1, n)

    def batch() -> None:
        kernel.sma(close, 20)
        kernel.ema(close, 20)
        kernel.ema(close, 50)
        kernel.rma(kernel.true_range(high, low, close), 14)
        kernel.wma(close, 20)
        kernel.stdev(close, 20)
        kernel.rolling_max(high, 20)
        kernel.rolling_min(low, 20)
        kernel.ema(close, 200)
        kernel.rma(close, 14)

    batch()  # warm up: import machinery, numpy's first-call cache

    start = time.perf_counter()
    batch()
    elapsed = time.perf_counter() - start

    assert elapsed < GENEROUS_BOUND_SECONDS, (
        f"a batch of 10 indicators on {n} candles took {elapsed * 1000:.1f}ms — "
        f"REQUEST_CEILING in routers/indicators.py assumes this stays well under "
        f"{GENEROUS_BOUND_SECONDS * 1000:.0f}ms"
    )
