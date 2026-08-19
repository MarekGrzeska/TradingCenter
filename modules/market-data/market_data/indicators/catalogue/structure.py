"""Rare events and reference lines: swings, clusters, and levels from a coarser series.

Two halves that share nothing but their output shapes. The first computes from the
series being drawn over; the second is handed one closed candle of a higher resolution
by the router and never sees a series at all (docs/wskazniki-plan-wdrozenia.html,
"W1 — punkty i poziomy").
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from ...models import Resolution
from .. import kernel
from .spec import (
    ClusterLevel,
    ClusterLevels,
    HtfLevel,
    HtfLevels,
    HtfLevelsFn,
    IndicatorSpec,
    Lines,
    LineSpec,
    MarkerPoint,
    Markers,
    Param,
    Render,
    Series,
    Warmup,
)

# side make a fractal — and every entry below takes it as its own parameter
# rather than assuming a shared default, so a caller composing e.g. `swing_points`
# with `level_clusters` is the one who decides they agree. ---


def _swing_extremes(high: np.ndarray, low: np.ndarray, n: int) -> tuple[np.ndarray, np.ndarray]:
    """Bar `i` is a swing high when `high[i]` is strictly greater than each of the
    `n` bars on both sides — a Williams fractal. `True` only once those `n` bars
    *after* `i` exist in the array; turning "not yet confirmed" into a gap rather
    than a repainted answer is the caller's job (`_compute_swing_points`,
    `_last_swing_series`), not this function's.
    """
    length = len(high)
    if n < 1 or length < 2 * n + 1:
        return np.zeros(length, dtype=bool), np.zeros(length, dtype=bool)
    is_high = np.ones(length, dtype=bool)
    is_low = np.ones(length, dtype=bool)
    with np.errstate(invalid="ignore"):
        for k in range(1, n + 1):
            is_high &= high > kernel.shift(high, k)
            is_high &= high > kernel.lead(high, k)
            is_low &= low < kernel.shift(low, k)
            is_low &= low < kernel.lead(low, k)
    return is_high, is_low


def _compute_swing_points(s: Series, p: Mapping[str, float]) -> list[MarkerPoint]:
    n = int(p["n"])
    is_high, is_low = _swing_extremes(s.high, s.low, n)
    points: list[MarkerPoint] = []
    for i in range(len(s)):
        if is_high[i]:
            points.append(MarkerPoint(bar=i, label="Swing High", price=float(s.high[i])))
        if is_low[i]:
            points.append(MarkerPoint(bar=i, label="Swing Low", price=float(s.low[i])))
    return points


_SWING_POINTS = IndicatorSpec(
    id="swing_points",
    name="Swing Points",
    group="structure",
    aliases=("Fraktale Williamsa", "Williams Fractal"),
    inputs=("high", "low"),
    params=(Param(name="n", type="int", default=2, min=1, max=50),),
    render=Render(pane="price", style="dots"),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["n"])),
    computer=Markers(_compute_swing_points),
)


def _last_swing_series(is_extreme: np.ndarray, price_at_extreme: np.ndarray, n: int) -> np.ndarray:
    """The most recently *confirmed* extreme's price, carried forward as a step.
    Confirmation lands `n` bars after the extreme itself, so the step moves at
    bar `i + n`, never at `i` — the value at any bar only ever uses what a reader
    stopping at that bar could already have known; nothing here repaints."""
    length = len(is_extreme)
    out = np.full(length, np.nan, dtype=np.float64)
    last_value = np.nan
    for j in range(length):
        confirmed_i = j - n
        if confirmed_i >= 0 and is_extreme[confirmed_i]:
            last_value = price_at_extreme[confirmed_i]
        out[j] = last_value
    return out


def _compute_last_swing_high(s: Series, p: Mapping[str, float]) -> dict[str, np.ndarray]:
    n = int(p["n"])
    is_high, _is_low = _swing_extremes(s.high, s.low, n)
    return {"last_swing_high": _last_swing_series(is_high, s.high, n)}


def _compute_last_swing_low(s: Series, p: Mapping[str, float]) -> dict[str, np.ndarray]:
    n = int(p["n"])
    _is_high, is_low = _swing_extremes(s.high, s.low, n)
    return {"last_swing_low": _last_swing_series(is_low, s.low, n)}


_LAST_SWING_HIGH = IndicatorSpec(
    id="last_swing_high",
    name="Last Swing High",
    group="structure",
    inputs=("high", "low"),
    params=(Param(name="n", type="int", default=2, min=1, max=50),),
    lines=(LineSpec(key="last_swing_high", label="Last Swing High {n}"),),
    render=Render(pane="price", style="line", autoscale=True),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["n"])),
    computer=Lines(_compute_last_swing_high),
)

_LAST_SWING_LOW = IndicatorSpec(
    id="last_swing_low",
    name="Last Swing Low",
    group="structure",
    inputs=("high", "low"),
    params=(Param(name="n", type="int", default=2, min=1, max=50),),
    lines=(LineSpec(key="last_swing_low", label="Last Swing Low {n}"),),
    render=Render(pane="price", style="line", autoscale=True),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["n"])),
    computer=Lines(_compute_last_swing_low),
)

_ROLLING_EXTREME = IndicatorSpec(
    id="rolling_extreme",
    name="Rolling Extreme",
    group="structure",
    aliases=("HHV/LLV",),
    inputs=("high", "low"),
    params=(Param(name="n", type="int", default=20, min=2, max=5000),),
    lines=(
        LineSpec(key="upper", label="Rolling High {n}"),
        LineSpec(key="lower", label="Rolling Low {n}"),
    ),
    render=Render(pane="price", style="line"),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["n"])),
    computer=Lines(lambda s, p: {
        "upper": kernel.rolling_max(s.high, int(p["n"])),
        "lower": kernel.rolling_min(s.low, int(p["n"])),
    }),
)


def _cluster_points(
    points: list[tuple[int, float]], tolerance: float, label: str
) -> list[ClusterLevel]:
    """Greedy 1-D clustering, closest price first: a point joins the running
    cluster while it sits within `tolerance` of that cluster's *first* (lowest)
    member, else it starts a new one. `bar` reported is the second-earliest
    member's — the moment a cluster of two or more extrema first exists."""
    if tolerance <= 0 or len(points) < 2:
        return []
    ordered = sorted(points, key=lambda pt: pt[1])
    clusters: list[list[tuple[int, float]]] = []
    current: list[tuple[int, float]] = []
    for bar, price in ordered:
        if current and price - current[0][1] > tolerance:
            clusters.append(current)
            current = []
        current.append((bar, price))
    if current:
        clusters.append(current)

    out: list[ClusterLevel] = []
    for cluster in clusters:
        if len(cluster) < 2:
            continue
        by_time = sorted(cluster, key=lambda pt: pt[0])
        out.append(
            ClusterLevel(
                bar=by_time[1][0],
                price=sum(pt[1] for pt in cluster) / len(cluster),
                label=label,
                count=len(cluster),
            )
        )
    return out


def _compute_level_clusters(s: Series, p: Mapping[str, float]) -> list[ClusterLevel]:
    n = int(p["n"])
    tol = float(p["tol"])
    atr_period = int(p["atr_period"])
    is_high, is_low = _swing_extremes(s.high, s.low, n)
    atr = kernel.rma(kernel.true_range(s.high, s.low, s.close), atr_period)
    reference_atr = float(atr[-1]) if len(atr) else 0.0
    tolerance = tol * reference_atr

    highs = [(i, float(s.high[i])) for i in range(len(s)) if is_high[i]]
    lows = [(i, float(s.low[i])) for i in range(len(s)) if is_low[i]]
    return _cluster_points(highs, tolerance, "Equal High") + _cluster_points(
        lows, tolerance, "Equal Low"
    )


_LEVEL_CLUSTERS = IndicatorSpec(
    id="level_clusters",
    name="Level Clusters",
    group="structure",
    aliases=("Equal Highs / Lows", "EQH/EQL"),
    inputs=("high", "low", "close"),
    params=(
        Param(name="n", type="int", default=2, min=1, max=50),
        Param(name="tol", type="float", default=0.1, min=0.0, max=5.0),
        Param(name="atr_period", type="int", default=14, min=2, max=5000),
    ),
    render=Render(pane="price", style="line"),
    warmup=Warmup(kind="fixed", bars=lambda p: max(int(p["n"]), int(p["atr_period"]))),
    computer=ClusterLevels(_compute_level_clusters),
)

# --- levels from a higher interval: a cross-resolution read of one closed period
# — a single DAY/WEEK candle, four or seven rays drawn out of it
# (docs/wskazniki-plan-wdrozenia.html, "htf_levels(okres)" and "pivots(typ, okres)").
# The period is a choice of catalogue id here, not a numeric parameter — the same
# choice `bbands_percent_b` already makes for its output shape instead of taking it
# as a `mode`. The router (`routers/indicators.py`) reads the series named in
# `higher_resolution` separately and hands the OHLC tuple of one closed candle down
# ready — none of the functions below ever sees the database. ---


def _htf_ohlc_levels(ohlc: tuple[float, float, float, float], prefix: str) -> list[HtfLevel]:
    o, h, lo, c = ohlc
    return [
        HtfLevel(o, f"{prefix} Open"),
        HtfLevel(h, f"{prefix} High"),
        HtfLevel(lo, f"{prefix} Low"),
        HtfLevel(c, f"{prefix} Close"),
    ]


_HTF_LEVELS_DAY = IndicatorSpec(
    id="htf_levels_day",
    name="Previous Day Levels",
    group="structure",
    aliases=("PDH/PDL",),
    inputs=("open", "high", "low", "close"),
    render=Render(pane="price", style="line"),
    warmup=Warmup(kind="fixed", bars=lambda p: 0),
    computer=HtfLevels(lambda ohlc: _htf_ohlc_levels(ohlc, "PD"), Resolution.DAY),
)

_HTF_LEVELS_WEEK = IndicatorSpec(
    id="htf_levels_week",
    name="Previous Week Levels",
    group="structure",
    aliases=("PWH/PWL",),
    inputs=("open", "high", "low", "close"),
    render=Render(pane="price", style="line"),
    warmup=Warmup(kind="fixed", bars=lambda p: 0),
    computer=HtfLevels(lambda ohlc: _htf_ohlc_levels(ohlc, "PW"), Resolution.WEEK),
)


def _pivots_classic(ohlc: tuple[float, float, float, float]) -> list[HtfLevel]:
    _o, h, lo, c = ohlc
    pp = (h + lo + c) / 3
    r1, s1 = 2 * pp - lo, 2 * pp - h
    r2, s2 = pp + (h - lo), pp - (h - lo)
    r3, s3 = h + 2 * (pp - lo), lo - 2 * (h - pp)
    return [
        HtfLevel(r3, "R3"),
        HtfLevel(r2, "R2"),
        HtfLevel(r1, "R1"),
        HtfLevel(pp, "PP"),
        HtfLevel(s1, "S1"),
        HtfLevel(s2, "S2"),
        HtfLevel(s3, "S3"),
    ]


def _pivots_fibonacci(ohlc: tuple[float, float, float, float]) -> list[HtfLevel]:
    _o, h, lo, c = ohlc
    pp = (h + lo + c) / 3
    span = h - lo
    return [
        HtfLevel(pp + span, "R3"),
        HtfLevel(pp + 0.618 * span, "R2"),
        HtfLevel(pp + 0.382 * span, "R1"),
        HtfLevel(pp, "PP"),
        HtfLevel(pp - 0.382 * span, "S1"),
        HtfLevel(pp - 0.618 * span, "S2"),
        HtfLevel(pp - span, "S3"),
    ]


def _pivots_camarilla(ohlc: tuple[float, float, float, float]) -> list[HtfLevel]:
    _o, h, lo, c = ohlc
    span = h - lo
    return [
        HtfLevel(c + span * 1.1 / 2, "R4"),
        HtfLevel(c + span * 1.1 / 4, "R3"),
        HtfLevel(c + span * 1.1 / 6, "R2"),
        HtfLevel(c + span * 1.1 / 12, "R1"),
        HtfLevel(c - span * 1.1 / 12, "S1"),
        HtfLevel(c - span * 1.1 / 6, "S2"),
        HtfLevel(c - span * 1.1 / 4, "S3"),
        HtfLevel(c - span * 1.1 / 2, "S4"),
    ]


def _pivots_woodie(ohlc: tuple[float, float, float, float]) -> list[HtfLevel]:
    _o, h, lo, c = ohlc
    pp = (h + lo + 2 * c) / 4
    r1, s1 = 2 * pp - lo, 2 * pp - h
    r2, s2 = pp + (h - lo), pp - (h - lo)
    return [
        HtfLevel(r2, "R2"),
        HtfLevel(r1, "R1"),
        HtfLevel(pp, "PP"),
        HtfLevel(s1, "S1"),
        HtfLevel(s2, "S2"),
    ]


def _pivots_demark(ohlc: tuple[float, float, float, float]) -> list[HtfLevel]:
    o, h, lo, c = ohlc
    if c < o:
        x = h + 2 * lo + c
    elif c > o:
        x = 2 * h + lo + c
    else:
        x = h + lo + 2 * c
    pp = x / 4
    return [HtfLevel(x / 2 - lo, "R1"), HtfLevel(pp, "PP"), HtfLevel(x / 2 - h, "S1")]


_PIVOT_TYPES: tuple[tuple[str, str, HtfLevelsFn], ...] = (
    ("pivots_classic", "Pivot Points (Classic)", _pivots_classic),
    ("pivots_fibonacci", "Pivot Points (Fibonacci)", _pivots_fibonacci),
    ("pivots_camarilla", "Pivot Points (Camarilla)", _pivots_camarilla),
    ("pivots_woodie", "Pivot Points (Woodie)", _pivots_woodie),
    ("pivots_demark", "Pivot Points (DeMark)", _pivots_demark),
)

_PIVOTS: tuple[IndicatorSpec, ...] = tuple(
    IndicatorSpec(
        id=id_,
        name=name,
        group="structure",
        inputs=("open", "high", "low", "close"),
        render=Render(pane="price", style="line"),
        warmup=Warmup(kind="fixed", bars=lambda p: 0),
        computer=HtfLevels(fn, Resolution.DAY),
    )
    for id_, name, fn in _PIVOT_TYPES
)


STRUCTURE: tuple[IndicatorSpec, ...] = (
    _SWING_POINTS,
    _LAST_SWING_HIGH,
    _LAST_SWING_LOW,
    _ROLLING_EXTREME,
    _LEVEL_CLUSTERS,
    _HTF_LEVELS_DAY,
    _HTF_LEVELS_WEEK,
    *_PIVOTS,
)
