"""Bounded measures, mostly for divergence-hunting. Every threshold they are usually read against
is a `render.levels` hint the caller may ignore, never a verdict baked into the value."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from .. import kernel, warmup
from .arithmetic import safe_divide
from .spec import IndicatorSpec, Lines, LineSpec, Param, Render, Series, Warmup


def _rsi_values(close: np.ndarray, period: int) -> np.ndarray:
    change = kernel.diff(close, 1)
    # Bar 0 has no earlier bar to change from — read as "0 change", not "unknown": `rma` seeds
    # recursively from index 0, and a NaN seed poisons every bar after it.
    no_prior_bar = np.isnan(change)
    gains = np.where(no_prior_bar, 0.0, np.maximum(change, 0.0))
    losses = np.where(no_prior_bar, 0.0, np.maximum(-change, 0.0))
    rs = safe_divide(kernel.rma(gains, period), kernel.rma(losses, period))
    return 100 - 100 / (1 + rs)


_RSI = IndicatorSpec(
    id="rsi",
    name="Relative Strength Index",
    group="oscillators",
    params=(Param(name="period", type="int", default=14, min=2, max=5000),),
    lines=(LineSpec(key="rsi", label="RSI {period}"),),
    render=Render(
        pane="own", style="line", scale="fixed", range=(0.0, 100.0), autoscale=False, levels=(30.0, 70.0)
    ),
    warmup=Warmup(kind="decay", bars=lambda p: warmup.rma_warmup_bars(int(p["period"]))),
    computer=Lines(lambda s, p: {"rsi": _rsi_values(s.close, int(p["period"]))}),
)


def _compute_macd(s: Series, p: Mapping[str, float]) -> dict[str, np.ndarray]:
    macd_line = kernel.ema(s.close, int(p["fast_period"])) - kernel.ema(s.close, int(p["slow_period"]))
    signal_line = kernel.ema(macd_line, int(p["signal_period"]))
    return {"macd": macd_line, "signal": signal_line, "histogram": macd_line - signal_line}


_MACD = IndicatorSpec(
    id="macd",
    name="Moving Average Convergence Divergence",
    group="oscillators",
    params=(
        Param(name="fast_period", type="int", default=12, min=2, max=5000),
        Param(name="slow_period", type="int", default=26, min=2, max=5000),
        Param(name="signal_period", type="int", default=9, min=2, max=5000),
    ),
    lines=(
        LineSpec(key="macd", label="MACD {fast_period},{slow_period}"),
        LineSpec(key="signal", label="Signal {signal_period}"),
        LineSpec(key="histogram", label="Histogram", style="histogram"),
    ),
    render=Render(pane="own", style="line", scale="own", autoscale=True),
    # The slow EMA's own decay plus the signal EMA's stacked on top, the same two-stage recursion
    # as `adx`: `signal` is an `ema` of a series that already contains an unstabilised one.
    warmup=Warmup(
        kind="decay",
        bars=lambda p: warmup.ema_warmup_bars(int(p["slow_period"]))
        + warmup.ema_warmup_bars(int(p["signal_period"])),
    ),
    computer=Lines(_compute_macd),
)


def _compute_stoch(s: Series, p: Mapping[str, float]) -> dict[str, np.ndarray]:
    k_period = int(p["k_period"])
    lowest = kernel.rolling_min(s.low, k_period)
    highest = kernel.rolling_max(s.high, k_period)
    raw_k = 100 * safe_divide(s.close - lowest, highest - lowest)
    k = kernel.sma(raw_k, int(p["k_smooth"]))
    d = kernel.sma(k, int(p["d_period"]))
    return {"k": k, "d": d}


_STOCH = IndicatorSpec(
    id="stoch",
    name="Stochastic Oscillator",
    group="oscillators",
    inputs=("high", "low", "close"),
    params=(
        Param(name="k_period", type="int", default=14, min=2, max=5000),
        Param(name="k_smooth", type="int", default=3, min=1, max=500),
        Param(name="d_period", type="int", default=3, min=1, max=500),
    ),
    lines=(
        LineSpec(key="k", label="%K {k_period}"),
        LineSpec(key="d", label="%D {d_period}"),
    ),
    render=Render(
        pane="own", style="line", scale="fixed", range=(0.0, 100.0), autoscale=False, levels=(20.0, 80.0)
    ),
    warmup=Warmup(
        kind="fixed",
        bars=lambda p: int(p["k_period"]) + int(p["k_smooth"]) + int(p["d_period"]),
    ),
    computer=Lines(_compute_stoch),
)


def _compute_stoch_rsi(s: Series, p: Mapping[str, float]) -> dict[str, np.ndarray]:
    rsi = _rsi_values(s.close, int(p["rsi_period"]))
    stoch_period = int(p["stoch_period"])
    lowest = kernel.rolling_min(rsi, stoch_period)
    highest = kernel.rolling_max(rsi, stoch_period)
    raw_k = 100 * safe_divide(rsi - lowest, highest - lowest)
    k = kernel.sma(raw_k, int(p["k_smooth"]))
    d = kernel.sma(k, int(p["d_period"]))
    return {"k": k, "d": d}


_STOCH_RSI = IndicatorSpec(
    id="stoch_rsi",
    name="Stochastic RSI",
    group="oscillators",
    params=(
        Param(name="rsi_period", type="int", default=14, min=2, max=5000),
        Param(name="stoch_period", type="int", default=14, min=2, max=5000),
        Param(name="k_smooth", type="int", default=3, min=1, max=500),
        Param(name="d_period", type="int", default=3, min=1, max=500),
    ),
    lines=(
        LineSpec(key="k", label="StochRSI %K {rsi_period},{stoch_period}"),
        LineSpec(key="d", label="StochRSI %D {d_period}"),
    ),
    render=Render(
        pane="own", style="line", scale="fixed", range=(0.0, 100.0), autoscale=False, levels=(20.0, 80.0)
    ),
    warmup=Warmup(
        kind="decay",
        bars=lambda p: warmup.rma_warmup_bars(int(p["rsi_period"]))
        + int(p["stoch_period"])
        + int(p["k_smooth"])
        + int(p["d_period"]),
    ),
    computer=Lines(_compute_stoch_rsi),
)


def _compute_cci(s: Series, p: Mapping[str, float]) -> dict[str, np.ndarray]:
    period = int(p["period"])
    typical = (s.high + s.low + s.close) / 3
    deviation = 0.015 * kernel.mean_abs_dev(typical, period)
    return {"cci": safe_divide(typical - kernel.sma(typical, period), deviation)}


_CCI = IndicatorSpec(
    id="cci",
    name="Commodity Channel Index",
    group="oscillators",
    inputs=("high", "low", "close"),
    params=(Param(name="period", type="int", default=20, min=2, max=5000),),
    lines=(LineSpec(key="cci", label="CCI {period}"),),
    render=Render(pane="own", style="line", scale="own", autoscale=True),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["period"])),
    computer=Lines(_compute_cci),
)

_ROC = IndicatorSpec(
    id="roc",
    name="Rate of Change",
    group="oscillators",
    params=(Param(name="period", type="int", default=9, min=1, max=5000),),
    lines=(LineSpec(key="roc", label="ROC {period}"),),
    render=Render(pane="own", style="line", scale="own", autoscale=True),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["period"])),
    computer=Lines(lambda s, p: {
        "roc": 100
        * safe_divide(
            s.close - kernel.shift(s.close, int(p["period"])), kernel.shift(s.close, int(p["period"]))
        )
    }),
)

_WILLIAMS_R = IndicatorSpec(
    id="williams_r",
    name="Williams %R",
    group="oscillators",
    inputs=("high", "low", "close"),
    params=(Param(name="period", type="int", default=14, min=2, max=5000),),
    lines=(LineSpec(key="williams_r", label="Williams %R {period}"),),
    render=Render(
        pane="own",
        style="line",
        scale="fixed",
        range=(-100.0, 0.0),
        autoscale=False,
        levels=(-20.0, -80.0),
    ),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["period"])),
    computer=Lines(lambda s, p: {
        "williams_r": -100
        * safe_divide(
            kernel.rolling_max(s.high, int(p["period"])) - s.close,
            kernel.rolling_max(s.high, int(p["period"])) - kernel.rolling_min(s.low, int(p["period"])),
        )
    }),
)


def _compute_cmo(s: Series, p: Mapping[str, float]) -> dict[str, np.ndarray]:
    period = int(p["period"])
    change = kernel.diff(s.close, 1)
    no_prior_bar = np.isnan(change)
    gains = np.where(no_prior_bar, 0.0, np.maximum(change, 0.0))
    losses = np.where(no_prior_bar, 0.0, np.maximum(-change, 0.0))
    sum_gain = kernel.sma(gains, period) * period
    sum_loss = kernel.sma(losses, period) * period
    return {"cmo": 100 * safe_divide(sum_gain - sum_loss, sum_gain + sum_loss)}


_CMO = IndicatorSpec(
    id="cmo",
    name="Chande Momentum Oscillator",
    group="oscillators",
    params=(Param(name="period", type="int", default=9, min=2, max=5000),),
    lines=(LineSpec(key="cmo", label="CMO {period}"),),
    render=Render(pane="own", style="line", scale="fixed", range=(-100.0, 100.0), autoscale=False),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["period"])),
    computer=Lines(_compute_cmo),
)


OSCILLATORS: tuple[IndicatorSpec, ...] = (
    _RSI,
    _MACD,
    _STOCH,
    _STOCH_RSI,
    _CCI,
    _ROC,
    _WILLIAMS_R,
    _CMO,
)
