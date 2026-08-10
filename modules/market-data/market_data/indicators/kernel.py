"""The math, and nothing else.

No FastAPI, no asyncpg, no pydantic — this module takes arrays of floats and returns
arrays of floats. That is deliberate and load-bearing (design.md, "Obliczenia w
`market-data`, nie w nowym module"): the day these need to move to a process of their
own, moving this file is the whole migration, because it has nothing to disentangle
from the web framework or the database driver.

Every function is indexed by bar number, not by time — a caller lines the result up
against its own timestamps. `np.nan` marks an index a finite-window function cannot
answer yet (fewer than `period` samples behind it); a recursive one is never NaN, because
it is defined from its first sample onward. How far into a recursive series to trust the
answer is `warmup.py`'s question, not this module's — mixing the two would make a kernel
function's output depend on how it happens to be called, which is the one thing this
module exists to rule out.

Every operation runs at `float64` and every reduction has one fixed order — never a
parallel or tree reduction — because two orderings of the same sum can differ in the
last bit, and a wskaźnik that isn't the same twice isn't the product this module sells.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

# What every function here accepts: a plain sequence, for a caller building a series by
# hand, or the ndarray one function here hands to the next in the same catalogue entry.
FloatArray = Sequence[float] | np.ndarray


def _as_float64(values: FloatArray) -> np.ndarray:
    return np.asarray(values, dtype=np.float64)


def sma(values: FloatArray, period: int) -> np.ndarray:
    """Simple moving average. `np.nan` for the first `period - 1` bars."""
    arr = _as_float64(values)
    out = np.full(arr.shape, np.nan, dtype=np.float64)
    if period < 1 or len(arr) < period:
        return out
    windows = np.lib.stride_tricks.sliding_window_view(arr, period)
    out[period - 1 :] = windows.mean(axis=1)
    return out


def wma(values: FloatArray, period: int) -> np.ndarray:
    """Linearly weighted moving average — the most recent bar in a window weighs
    `period` times as much as the oldest one."""
    arr = _as_float64(values)
    out = np.full(arr.shape, np.nan, dtype=np.float64)
    if period < 1 or len(arr) < period:
        return out
    weights = np.arange(1, period + 1, dtype=np.float64)
    windows = np.lib.stride_tricks.sliding_window_view(arr, period)
    out[period - 1 :] = windows @ weights / weights.sum()
    return out


def stdev(values: FloatArray, period: int, ddof: int = 0) -> np.ndarray:
    """Rolling standard deviation. Population (`ddof=0`) by default — the same
    convention `bbands` in the catalogue depends on, so the two never disagree."""
    arr = _as_float64(values)
    out = np.full(arr.shape, np.nan, dtype=np.float64)
    if period < 1 or len(arr) < period:
        return out
    windows = np.lib.stride_tricks.sliding_window_view(arr, period)
    out[period - 1 :] = windows.std(axis=1, ddof=ddof)
    return out


def rolling_max(values: FloatArray, period: int) -> np.ndarray:
    arr = _as_float64(values)
    out = np.full(arr.shape, np.nan, dtype=np.float64)
    if period < 1 or len(arr) < period:
        return out
    windows = np.lib.stride_tricks.sliding_window_view(arr, period)
    out[period - 1 :] = windows.max(axis=1)
    return out


def rolling_min(values: FloatArray, period: int) -> np.ndarray:
    arr = _as_float64(values)
    out = np.full(arr.shape, np.nan, dtype=np.float64)
    if period < 1 or len(arr) < period:
        return out
    windows = np.lib.stride_tricks.sliding_window_view(arr, period)
    out[period - 1 :] = windows.min(axis=1)
    return out


def _recursive_smoothing(values: FloatArray, alpha: float) -> np.ndarray:
    """`out[0] = values[0]`, `out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]`.

    Seeded with the first sample rather than an early SMA on purpose: `warmup.py`'s
    formula for how many bars a filter needs is the weight of exactly this seed decaying
    below `1e-9`, and seeding any other way would make that formula describe a filter
    this function does not implement.

    A Python loop, not a vectorised one — there is no vectorised form of a first-order
    recursive filter, and at the sizes this module reads (a few thousand bars) the loop
    costs low single-digit milliseconds, measured in `test_kernel_performance.py`.
    """
    arr = _as_float64(values)
    out = np.empty(arr.shape, dtype=np.float64)
    if len(arr) == 0:
        return out
    out[0] = arr[0]
    for i in range(1, len(arr)):
        out[i] = alpha * arr[i] + (1 - alpha) * out[i - 1]
    return out


def ema(values: FloatArray, period: int) -> np.ndarray:
    """Exponential moving average, `alpha = 2 / (period + 1)`. Defined from the first
    bar onward — see `warmup.ema_warmup_bars` for how many of those bars to distrust."""
    return _recursive_smoothing(values, alpha=2.0 / (period + 1))


def rma(values: FloatArray, period: int) -> np.ndarray:
    """Wilder's smoothing, `alpha = 1 / period` — the slower-decaying sibling of `ema`
    that `atr`, `rsi` and `adx` are all built from."""
    return _recursive_smoothing(values, alpha=1.0 / period)


def true_range(high: FloatArray, low: FloatArray, close: FloatArray) -> np.ndarray:
    """The greatest of today's range and today's move from yesterday's close.

    The first bar has no previous close to gap from, so it falls back to the bar's own
    range — the same thing every later bar would compute if yesterday's close happened
    to equal today's open.
    """
    high_arr, low_arr, close_arr = _as_float64(high), _as_float64(low), _as_float64(close)
    out = high_arr - low_arr
    if len(close_arr) > 1:
        prev_close = close_arr[:-1]
        gap_up = np.abs(high_arr[1:] - prev_close)
        gap_down = np.abs(low_arr[1:] - prev_close)
        out[1:] = np.maximum(out[1:], np.maximum(gap_up, gap_down))
    return out
