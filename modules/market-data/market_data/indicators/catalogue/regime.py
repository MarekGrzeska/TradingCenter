"""Whether there is a trend at all — the question the geometry ratios do not answer.

A "break of structure" means nothing until something here says the market was trending
in the first place (docs/wskazniki-plan-wdrozenia.html, "Reżim").
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from .. import kernel, warmup
from .arithmetic import safe_divide
from .spec import IndicatorSpec, Lines, LineSpec, Param, Render, Series, Warmup

# before it means anything (docs/wskazniki-plan-wdrozenia.html, "Reżim"). ---


def _compute_adx(s: Series, p: Mapping[str, float]) -> dict[str, np.ndarray]:
    period = int(p["period"])
    up_move = np.diff(s.high, prepend=s.high[0])
    down_move = -np.diff(s.low, prepend=s.low[0])
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr_smoothed = kernel.rma(kernel.true_range(s.high, s.low, s.close), period)
    plus_di = 100 * safe_divide(kernel.rma(plus_dm, period), tr_smoothed)
    minus_di = 100 * safe_divide(kernel.rma(minus_dm, period), tr_smoothed)
    # `+DI` and `-DI` both land on exactly 0 at bar 0 — there is no earlier bar to
    # measure directional movement against — which makes their sum 0 too. Read as
    # "no directional dominance either way" (0), not "undefined" (NaN): `rma` seeds
    # recursively from bar 0, and a NaN seed would poison every bar after it,
    # forever, rather than merely decaying the way a seed is meant to.
    di_sum = plus_di + minus_di
    dx = np.where(di_sum == 0, 0.0, 100 * np.abs(plus_di - minus_di) / np.where(di_sum == 0, 1.0, di_sum))
    return {"adx": kernel.rma(dx, period), "plus_di": plus_di, "minus_di": minus_di}


_ADX = IndicatorSpec(
    id="adx",
    name="Average Directional Index",
    group="regime",
    aliases=("Directional Movement Index",),
    inputs=("high", "low", "close"),
    params=(Param(name="period", type="int", default=14, min=2, max=5000),),
    lines=(
        LineSpec(key="adx", label="ADX {period}"),
        LineSpec(key="plus_di", label="+DI {period}"),
        LineSpec(key="minus_di", label="-DI {period}"),
    ),
    render=Render(pane="own", style="line", scale="fixed", range=(0.0, 100.0), autoscale=False),
    # Doubly smoothed — DX is already an `rma` of the directional movement, and ADX
    # is an `rma` of DX on top — so the seed's influence takes roughly twice as long
    # to decay below epsilon as one `rma` alone (design.md, "Głębokość archiwum":
    # ADX(14) needs ~580 bars, close to 2 × rma_warmup_bars(14) ≈ 560).
    warmup=Warmup(kind="decay", bars=lambda p: 2 * warmup.rma_warmup_bars(int(p["period"]))),
    computer=Lines(_compute_adx),
)


def _compute_choppiness(s: Series, p: Mapping[str, float]) -> dict[str, np.ndarray]:
    period = int(p["period"])
    tr_sum = kernel.sma(kernel.true_range(s.high, s.low, s.close), period) * period
    range_hl = kernel.rolling_max(s.high, period) - kernel.rolling_min(s.low, period)
    ratio = safe_divide(tr_sum, range_hl)
    return {"choppiness": 100 * np.log10(ratio) / np.log10(period)}


_CHOPPINESS = IndicatorSpec(
    id="choppiness",
    name="Choppiness Index",
    group="regime",
    inputs=("high", "low", "close"),
    params=(Param(name="period", type="int", default=14, min=2, max=5000),),
    lines=(LineSpec(key="choppiness", label="Choppiness {period}"),),
    render=Render(pane="own", style="line", scale="fixed", range=(0.0, 100.0), autoscale=False),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["period"])),
    computer=Lines(_compute_choppiness),
)


def _compute_aroon(s: Series, p: Mapping[str, float]) -> dict[str, np.ndarray]:
    period = int(p["period"])
    # A `period + 1`-bar window, not `period` — "days since the extreme" counts
    # today as day zero and looks back `period` days from it, which is
    # `period + 1` candles end to end (Chande's original definition, and
    # TA-Lib's; a plain `period`-bar window can never report "the extreme is
    # today", the one case this caught when checked against TA-Lib in 2.11).
    bars_since_high = kernel.rolling_argmax(s.high, period + 1)
    bars_since_low = kernel.rolling_argmin(s.low, period + 1)
    return {
        "aroon_up": 100 * (period - bars_since_high) / period,
        "aroon_down": 100 * (period - bars_since_low) / period,
    }


_AROON = IndicatorSpec(
    id="aroon",
    name="Aroon",
    group="regime",
    inputs=("high", "low"),
    params=(Param(name="period", type="int", default=14, min=2, max=5000),),
    lines=(
        LineSpec(key="aroon_up", label="Aroon Up {period}"),
        LineSpec(key="aroon_down", label="Aroon Down {period}"),
    ),
    render=Render(pane="own", style="line", scale="fixed", range=(0.0, 100.0), autoscale=False),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["period"]) + 1),
    computer=Lines(_compute_aroon),
)


def _compute_vortex(s: Series, p: Mapping[str, float]) -> dict[str, np.ndarray]:
    period = int(p["period"])
    prev_low = kernel.shift(s.low, 1)
    prev_high = kernel.shift(s.high, 1)
    vm_plus_sum = kernel.sma(np.abs(s.high - prev_low), period) * period
    vm_minus_sum = kernel.sma(np.abs(s.low - prev_high), period) * period
    tr_sum = kernel.sma(kernel.true_range(s.high, s.low, s.close), period) * period
    return {
        "vi_plus": safe_divide(vm_plus_sum, tr_sum),
        "vi_minus": safe_divide(vm_minus_sum, tr_sum),
    }


_VORTEX = IndicatorSpec(
    id="vortex",
    name="Vortex Indicator",
    group="regime",
    inputs=("high", "low", "close"),
    params=(Param(name="period", type="int", default=14, min=2, max=5000),),
    lines=(
        LineSpec(key="vi_plus", label="VI+ {period}"),
        LineSpec(key="vi_minus", label="VI- {period}"),
    ),
    render=Render(pane="own", style="line", scale="own", autoscale=True),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["period"]) + 1),
    computer=Lines(_compute_vortex),
)

_LINREG_SLOPE = IndicatorSpec(
    id="linreg_slope",
    name="Linear Regression Slope",
    group="regime",
    # Below 3, every window fits a line perfectly by construction — a slope
    # without a fit to speak of, and `r_squared` a constant 1.
    params=(Param(name="period", type="int", default=14, min=3, max=5000),),
    lines=(LineSpec(key="linreg_slope", label="LinReg Slope {period}"),),
    render=Render(pane="own", style="line", scale="own", autoscale=True),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["period"])),
    computer=Lines(lambda s, p: {"linreg_slope": kernel.linreg_slope(s.close, int(p["period"]))}),
)

_R_SQUARED = IndicatorSpec(
    id="r_squared",
    name="R-Squared",
    group="regime",
    params=(Param(name="period", type="int", default=14, min=3, max=5000),),
    lines=(LineSpec(key="r_squared", label="R² {period}"),),
    render=Render(pane="own", style="line", scale="fixed", range=(0.0, 1.0), autoscale=False),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["period"])),
    computer=Lines(lambda s, p: {"r_squared": kernel.r_squared(s.close, int(p["period"]))}),
)


REGIME: tuple[IndicatorSpec, ...] = (
    _ADX,
    _CHOPPINESS,
    _AROON,
    _VORTEX,
    _LINREG_SLOPE,
    _R_SQUARED,
)
