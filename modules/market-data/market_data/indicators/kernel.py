"""The math, and nothing else: arrays of floats in, arrays of floats out. Every reduction has one
fixed order — two orderings differ in the last bit, and an indicator that isn't the same twice isn't."""

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
    """Seeded with the first sample rather than an early SMA: `warmup.py`'s formula is the weight of
    exactly this seed decaying, and a first-order recursive filter has no vectorised form."""
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


def rolling_argmax(values: FloatArray, period: int) -> np.ndarray:
    """Bars ago the trailing window's maximum sits. A tie favours the older bar (`np.argmax` keeps
    the first occurrence), so the count only grows on a tie, never shrinks."""
    arr = _as_float64(values)
    out = np.full(arr.shape, np.nan, dtype=np.float64)
    if period < 1 or len(arr) < period:
        return out
    windows = np.lib.stride_tricks.sliding_window_view(arr, period)
    out[period - 1 :] = (period - 1) - windows.argmax(axis=1)
    return out


def rolling_argmin(values: FloatArray, period: int) -> np.ndarray:
    """`rolling_argmax`'s sibling for the trailing window's minimum."""
    arr = _as_float64(values)
    out = np.full(arr.shape, np.nan, dtype=np.float64)
    if period < 1 or len(arr) < period:
        return out
    windows = np.lib.stride_tricks.sliding_window_view(arr, period)
    out[period - 1 :] = (period - 1) - windows.argmin(axis=1)
    return out


def _rolling_ols(values: FloatArray, period: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Ordinary least squares of each trailing window against `x = 0 .. period - 1`. Shared by three
    entries so they never disagree about the window; `r_squared` is undefined for a flat one, not 0."""
    arr = _as_float64(values)
    n = len(arr)
    slope = np.full(n, np.nan, dtype=np.float64)
    intercept = np.full(n, np.nan, dtype=np.float64)
    r_sq = np.full(n, np.nan, dtype=np.float64)
    if period < 2 or n < period:
        return slope, intercept, r_sq

    x = np.arange(period, dtype=np.float64)
    sum_x = x.sum()
    sum_x2 = (x * x).sum()
    denom = period * sum_x2 - sum_x * sum_x

    windows = np.lib.stride_tricks.sliding_window_view(arr, period)
    sum_y = windows.sum(axis=1)
    sum_y2 = (windows * windows).sum(axis=1)
    sum_xy = windows @ x

    b = (period * sum_xy - sum_x * sum_y) / denom
    a = (sum_y - b * sum_x) / period
    ss_tot = sum_y2 - (sum_y * sum_y) / period
    ss_res = sum_y2 - a * sum_y - b * sum_xy
    with np.errstate(invalid="ignore", divide="ignore"):
        r_squared_values = 1 - ss_res / ss_tot

    slope[period - 1 :] = b
    intercept[period - 1 :] = a
    r_sq[period - 1 :] = r_squared_values
    return slope, intercept, r_sq


def linreg(values: FloatArray, period: int) -> np.ndarray:
    """The trailing window's fitted regression line, read at its last point — what
    the catalogue offers as `lsma`, the least-squares moving average."""
    slope, intercept, _ = _rolling_ols(values, period)
    return intercept + slope * (period - 1)


def linreg_slope(values: FloatArray, period: int) -> np.ndarray:
    """The trailing window's fitted slope, in units per bar."""
    slope, _, _ = _rolling_ols(values, period)
    return slope


def r_squared(values: FloatArray, period: int) -> np.ndarray:
    """How well a straight line fits the trailing window — `1` for a perfect fit,
    `0` for none, `np.nan` for a window with no variance to fit at all."""
    _, _, r_sq = _rolling_ols(values, period)
    return r_sq


def mean_abs_dev(values: FloatArray, period: int) -> np.ndarray:
    """Rolling mean absolute deviation from the window's own mean — `cci`'s
    denominator."""
    arr = _as_float64(values)
    out = np.full(arr.shape, np.nan, dtype=np.float64)
    if period < 1 or len(arr) < period:
        return out
    windows = np.lib.stride_tricks.sliding_window_view(arr, period)
    means = windows.mean(axis=1, keepdims=True)
    out[period - 1 :] = np.abs(windows - means).mean(axis=1)
    return out


def shift(values: FloatArray, n: int) -> np.ndarray:
    """`values`, `n` bars back — `np.nan` for the first `n` bars, which have no
    such bar to read."""
    arr = _as_float64(values)
    out = np.full(arr.shape, np.nan, dtype=np.float64)
    if n < 1 or len(arr) <= n:
        return out
    out[n:] = arr[:-n]
    return out


def lead(values: FloatArray, n: int) -> np.ndarray:
    """`values`, `n` bars ahead — `shift`'s mirror image. Swing-point confirmation is what this is
    for; every other primitive here only ever looks backward."""
    arr = _as_float64(values)
    out = np.full(arr.shape, np.nan, dtype=np.float64)
    if n < 1 or len(arr) <= n:
        return out
    out[:-n] = arr[n:]
    return out


def diff(values: FloatArray, n: int = 1) -> np.ndarray:
    """`values[i] - values[i - n]` — the change over `n` bars."""
    arr = _as_float64(values)
    return arr - shift(arr, n)


def cross(a: FloatArray, b: FloatArray) -> np.ndarray:
    """`1.0` where `a` crosses above `b` this bar, `-1.0` below, `np.nan` for the first. Not read by
    any catalogue entry yet — a foundation primitive, added now so later stages spend on the indicator."""
    arr_a, arr_b = _as_float64(a), _as_float64(b)
    n = len(arr_a)
    out = np.full(n, np.nan, dtype=np.float64)
    if n < 2:
        return out
    prev_a, prev_b = arr_a[:-1], arr_b[:-1]
    cur_a, cur_b = arr_a[1:], arr_b[1:]
    result = np.zeros(n - 1, dtype=np.float64)
    result[(prev_a <= prev_b) & (cur_a > cur_b)] = 1.0
    result[(prev_a >= prev_b) & (cur_a < cur_b)] = -1.0
    out[1:] = result
    return out


def alma(values: FloatArray, period: int, offset: float, sigma: float) -> np.ndarray:
    """Arnaud Legoux moving average — `wma`'s sibling with a Gaussian weight instead of a linear ramp.
    A finite window, so no seed to warm up."""
    arr = _as_float64(values)
    out = np.full(arr.shape, np.nan, dtype=np.float64)
    if period < 1 or len(arr) < period:
        return out
    m = offset * (period - 1)
    s = period / sigma
    j = np.arange(period, dtype=np.float64)
    weights = np.exp(-((j - m) ** 2) / (2 * s * s))
    windows = np.lib.stride_tricks.sliding_window_view(arr, period)
    out[period - 1 :] = windows @ weights / weights.sum()
    return out


def kama(values: FloatArray, period: int, fast: int, slow: int) -> np.ndarray:
    """Kaufman's adaptive moving average, whose smoothing constant tightens while the market trends.
    `warmup.kama_warmup_bars` bounds the seed with `slow` alone, which only ever overestimates."""
    arr = _as_float64(values)
    n = len(arr)
    out = np.full(n, np.nan, dtype=np.float64)
    if period < 1 or n <= period:
        return out

    change = np.abs(arr[period:] - arr[:-period])
    abs_diff = np.abs(np.diff(arr))
    volatility = np.lib.stride_tricks.sliding_window_view(abs_diff, period).sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        efficiency_ratio = np.where(volatility != 0, change / volatility, 0.0)

    fast_sc = 2.0 / (fast + 1)
    slow_sc = 2.0 / (slow + 1)
    smoothing = (efficiency_ratio * (fast_sc - slow_sc) + slow_sc) ** 2

    out[period - 1] = arr[period - 1]
    for offset_i in range(len(smoothing)):
        i = period + offset_i
        out[i] = out[i - 1] + smoothing[offset_i] * (arr[i] - out[i - 1])
    return out


def true_range(high: FloatArray, low: FloatArray, close: FloatArray) -> np.ndarray:
    """The greatest of today's range and today's move from yesterday's close. The first bar has no
    previous close to gap from, so it falls back to its own range."""
    high_arr, low_arr, close_arr = _as_float64(high), _as_float64(low), _as_float64(close)
    out = high_arr - low_arr
    if len(close_arr) > 1:
        prev_close = close_arr[:-1]
        gap_up = np.abs(high_arr[1:] - prev_close)
        gap_down = np.abs(low_arr[1:] - prev_close)
        out[1:] = np.maximum(out[1:], np.maximum(gap_up, gap_down))
    return out
