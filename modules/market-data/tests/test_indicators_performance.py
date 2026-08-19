"""Task 2.17: is `REQUEST_CEILING` (routers/indicators.py, set from 1.2's
measurement on a 10-entry catalogue) still a safe number now that the
catalogue holds every entry E1 added — 44, not 3?

A regression guard, not a benchmark, same reasoning as
`test_kernel_performance.py`: CI hardware varies too much for a tight bound
to mean anything, so this checks a generous one, wide enough to survive a
slow runner, that exists to catch an accidental O(n²) creeping into a new
entry's formula — not to pin an exact number.
"""

from __future__ import annotations

import time

import numpy as np
from computers import LINE_ENTRIES, fn_of

from market_data.indicators.catalogue import CATALOGUE, IndicatorSpec, Lines, Series
from market_data.routers.indicators import REQUEST_CEILING

# Measured on the machine that set this: the full catalogue at exactly
# REQUEST_CEILING candles×entries costs ~63ms p95 (was ~16.5ms for 10 entries
# at 5000 candles in the first stage — the ceiling itself, not the per-entry cost,
# is what grew, and cells scale roughly linearly with either factor). Ten
# times that, so only a real regression trips it.
GENEROUS_BOUND_SECONDS = 0.63


def _synthetic_series(n: int) -> Series:
    i = np.arange(n, dtype=np.float64)
    close = 100 + 8 * np.sin(i / 37) + 0.01 * i + 3 * np.sin(i / 5.3)
    spread = 0.4 + 0.15 * np.abs(np.sin(i / 11))
    high = close + spread
    low = close - spread
    open_ = close - 0.3 * np.sin(i / 2.7)
    return Series(open=open_, high=high, low=low, close=close)


def _default_params(entry: IndicatorSpec) -> dict[str, float]:
    return {p.name: p.default for p in entry.params}


def test_full_catalogue_at_the_request_ceiling_stays_fast():
    """The worst case a single request can reach without being refused:
    every entry the catalogue offers, at however many candles that many
    entries allows under `REQUEST_CEILING`."""
    candles = REQUEST_CEILING // len(CATALOGUE)
    series = _synthetic_series(candles)

    def batch() -> None:
        for entry in LINE_ENTRIES:
            fn_of(entry, Lines)(series, _default_params(entry))

    batch()  # warm up: import machinery, numpy's first-call cache

    start = time.perf_counter()
    batch()
    elapsed = time.perf_counter() - start

    assert elapsed < GENEROUS_BOUND_SECONDS, (
        f"the full catalogue ({len(CATALOGUE)} entries) at the request ceiling "
        f"({candles} candles) took {elapsed * 1000:.1f}ms — REQUEST_CEILING assumes "
        f"this stays well under {GENEROUS_BOUND_SECONDS * 1000:.0f}ms"
    )
