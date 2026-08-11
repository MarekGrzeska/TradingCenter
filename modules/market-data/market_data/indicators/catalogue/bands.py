"""Envelopes around a moving centre, and the two readings derived from one.

`donchian` is also "where the last n bars' extremes sit" — the same number serving two
very different purposes (docs/wskazniki-plan-wdrozenia.html, "Wstęgi i kanały").
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from .. import kernel, warmup
from .arithmetic import safe_divide
from .spec import IndicatorSpec, LineSpec, Param, Render, Series, Warmup


def _bbands_edges(s: Series, p: Mapping[str, float]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    period = int(p["period"])
    mult = float(p["mult"])
    basis = kernel.sma(s.close, period)
    dev = mult * kernel.stdev(s.close, period)
    return basis + dev, basis, basis - dev


_BBANDS = IndicatorSpec(
    id="bbands",
    name="Bollinger Bands",
    group="bands",
    params=(
        Param(name="period", type="int", default=20, min=2, max=5000),
        Param(name="mult", type="float", default=2.0, min=0.1, max=10.0),
    ),
    lines=(
        LineSpec(key="upper", label="BB Upper {period}"),
        LineSpec(key="basis", label="BB Basis {period}"),
        LineSpec(key="lower", label="BB Lower {period}"),
    ),
    render=Render(pane="price", style="line"),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["period"])),
    compute=lambda s, p: dict(zip(("upper", "basis", "lower"), _bbands_edges(s, p), strict=True)),
)

def _compute_bbands_percent_b(s: Series, p: Mapping[str, float]) -> dict[str, np.ndarray]:
    upper, _basis, lower = _bbands_edges(s, p)
    return {"percent_b": safe_divide(s.close - lower, upper - lower)}


_BBANDS_PERCENT_B = IndicatorSpec(
    id="bbands_percent_b",
    name="Bollinger %B",
    group="bands",
    params=(
        Param(name="period", type="int", default=20, min=2, max=5000),
        Param(name="mult", type="float", default=2.0, min=0.1, max=10.0),
    ),
    lines=(LineSpec(key="percent_b", label="%B {period}"),),
    # Not pinned to [0, 1] like the geometry ratios in `volatility.py` — a price outside
    # its own bands is exactly what this line exists to show, and a fixed scale
    # would clip that off screen.
    render=Render(pane="own", style="line", scale="own", autoscale=True, levels=(0.0, 1.0)),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["period"])),
    compute=_compute_bbands_percent_b,
)


def _compute_bbands_bandwidth(s: Series, p: Mapping[str, float]) -> dict[str, np.ndarray]:
    upper, basis, lower = _bbands_edges(s, p)
    return {"bandwidth": safe_divide(upper - lower, basis)}


_BBANDS_BANDWIDTH = IndicatorSpec(
    id="bbands_bandwidth",
    name="Bollinger Bandwidth",
    group="bands",
    params=(
        Param(name="period", type="int", default=20, min=2, max=5000),
        Param(name="mult", type="float", default=2.0, min=0.1, max=10.0),
    ),
    lines=(LineSpec(key="bandwidth", label="Bandwidth {period}"),),
    render=Render(pane="own", style="line", scale="own", autoscale=True),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["period"])),
    compute=_compute_bbands_bandwidth,
)


def _compute_keltner(s: Series, p: Mapping[str, float]) -> dict[str, np.ndarray]:
    basis = kernel.ema(s.close, int(p["period"]))
    band = float(p["mult"]) * kernel.rma(
        kernel.true_range(s.high, s.low, s.close), int(p["atr_period"])
    )
    return {"upper": basis + band, "basis": basis, "lower": basis - band}


_KELTNER = IndicatorSpec(
    id="keltner",
    name="Keltner Channel",
    group="bands",
    inputs=("high", "low", "close"),
    params=(
        Param(name="period", type="int", default=20, min=2, max=5000),
        Param(name="atr_period", type="int", default=10, min=2, max=5000),
        Param(name="mult", type="float", default=2.0, min=0.1, max=10.0),
    ),
    lines=(
        LineSpec(key="upper", label="KC Upper {period}"),
        LineSpec(key="basis", label="KC Basis {period}"),
        LineSpec(key="lower", label="KC Lower {period}"),
    ),
    render=Render(pane="price", style="line"),
    warmup=Warmup(
        kind="decay",
        bars=lambda p: max(
            warmup.ema_warmup_bars(int(p["period"])), warmup.rma_warmup_bars(int(p["atr_period"]))
        ),
    ),
    compute=_compute_keltner,
)

def _compute_donchian(s: Series, p: Mapping[str, float]) -> dict[str, np.ndarray]:
    period = int(p["period"])
    upper = kernel.rolling_max(s.high, period)
    lower = kernel.rolling_min(s.low, period)
    return {"upper": upper, "basis": (upper + lower) / 2, "lower": lower}


_DONCHIAN = IndicatorSpec(
    id="donchian",
    name="Donchian Channel",
    group="bands",
    inputs=("high", "low"),
    params=(Param(name="period", type="int", default=20, min=2, max=5000),),
    lines=(
        LineSpec(key="upper", label="DC Upper {period}"),
        LineSpec(key="basis", label="DC Basis {period}"),
        LineSpec(key="lower", label="DC Lower {period}"),
    ),
    render=Render(pane="price", style="line"),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["period"])),
    compute=_compute_donchian,
)


def _compute_envelope(s: Series, p: Mapping[str, float]) -> dict[str, np.ndarray]:
    basis = kernel.sma(s.close, int(p["period"]))
    band = basis * float(p["percent"]) / 100
    return {"upper": basis + band, "basis": basis, "lower": basis - band}


_ENVELOPE = IndicatorSpec(
    id="envelope",
    name="Moving Average Envelope",
    group="bands",
    params=(
        Param(name="period", type="int", default=20, min=2, max=5000),
        Param(name="percent", type="float", default=2.5, min=0.1, max=50.0),
    ),
    lines=(
        LineSpec(key="upper", label="Envelope Upper {period}"),
        LineSpec(key="basis", label="Envelope Basis {period}"),
        LineSpec(key="lower", label="Envelope Lower {period}"),
    ),
    render=Render(pane="price", style="line"),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["period"])),
    compute=_compute_envelope,
)


BANDS: tuple[IndicatorSpec, ...] = (
    _BBANDS,
    _BBANDS_PERCENT_B,
    _BBANDS_BANDWIDTH,
    _KELTNER,
    _DONCHIAN,
    _ENVELOPE,
)
