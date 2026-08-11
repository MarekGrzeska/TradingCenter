"""Averages: bias and a reference point, all from the same handful of primitives.

`sma` and `ema` come first in the catalogue on purpose — they are the entries every
future average will sit beside (docs/wskazniki-plan-wdrozenia.html, "Średnie").
"""

from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np

from .. import kernel, warmup
from .spec import IndicatorSpec, LineSpec, Param, Render, Series, Warmup

_SMA = IndicatorSpec(
    id="sma",
    name="Simple Moving Average",
    group="averages",
    params=(Param(name="period", type="int", default=20, min=2, max=5000),),
    lines=(LineSpec(key="sma", label="SMA {period}"),),
    render=Render(pane="price", style="line"),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["period"])),
    compute=lambda s, p: {"sma": kernel.sma(s.close, int(p["period"]))},
)

_EMA = IndicatorSpec(
    id="ema",
    name="Exponential Moving Average",
    group="averages",
    params=(Param(name="period", type="int", default=20, min=2, max=5000),),
    lines=(LineSpec(key="ema", label="EMA {period}"),),
    render=Render(pane="price", style="line"),
    warmup=Warmup(kind="decay", bars=lambda p: warmup.ema_warmup_bars(int(p["period"]))),
    compute=lambda s, p: {"ema": kernel.ema(s.close, int(p["period"]))},
)


# and `ema` are already in the catalogue from the first stage. ---

_WMA = IndicatorSpec(
    id="wma",
    name="Weighted Moving Average",
    group="averages",
    params=(Param(name="period", type="int", default=20, min=2, max=5000),),
    lines=(LineSpec(key="wma", label="WMA {period}"),),
    render=Render(pane="price", style="line"),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["period"])),
    compute=lambda s, p: {"wma": kernel.wma(s.close, int(p["period"]))},
)

_RMA = IndicatorSpec(
    id="rma",
    name="Wilder's Smoothing",
    group="averages",
    aliases=("Smoothed Moving Average",),
    params=(Param(name="period", type="int", default=20, min=2, max=5000),),
    lines=(LineSpec(key="rma", label="RMA {period}"),),
    render=Render(pane="price", style="line"),
    warmup=Warmup(kind="decay", bars=lambda p: warmup.rma_warmup_bars(int(p["period"]))),
    compute=lambda s, p: {"rma": kernel.rma(s.close, int(p["period"]))},
)


def _compute_hma(s: Series, p: Mapping[str, float]) -> dict[str, np.ndarray]:
    period = int(p["period"])
    half_period = round(period / 2)
    sqrt_period = round(math.sqrt(period))
    raw = 2 * kernel.wma(s.close, half_period) - kernel.wma(s.close, period)
    return {"hma": kernel.wma(raw, sqrt_period)}


_HMA = IndicatorSpec(
    id="hma",
    name="Hull Moving Average",
    group="averages",
    params=(Param(name="period", type="int", default=20, min=4, max=5000),),
    lines=(LineSpec(key="hma", label="HMA {period}"),),
    render=Render(pane="price", style="line"),
    # `raw` needs `period` bars from the larger `wma` call inside it; the final
    # `wma` needs `sqrt_period` more valid `raw` values on top of that — the same
    # "sum of consecutive windows" rule `ulcer` and `stoch` use.
    warmup=Warmup(
        kind="fixed", bars=lambda p: int(p["period"]) + round(math.sqrt(int(p["period"])))
    ),
    compute=_compute_hma,
)

_KAMA = IndicatorSpec(
    id="kama",
    name="Kaufman's Adaptive Moving Average",
    group="averages",
    params=(
        Param(name="period", type="int", default=10, min=2, max=5000),
        Param(name="fast", type="int", default=2, min=1, max=100),
        Param(name="slow", type="int", default=30, min=2, max=500),
    ),
    lines=(LineSpec(key="kama", label="KAMA {period}"),),
    render=Render(pane="price", style="line"),
    warmup=Warmup(
        kind="decay",
        bars=lambda p: warmup.kama_warmup_bars(int(p["period"]), int(p["slow"])),
    ),
    compute=lambda s, p: {
        "kama": kernel.kama(s.close, int(p["period"]), int(p["fast"]), int(p["slow"]))
    },
)

_ALMA = IndicatorSpec(
    id="alma",
    name="Arnaud Legoux Moving Average",
    group="averages",
    params=(
        Param(name="period", type="int", default=20, min=2, max=5000),
        Param(name="offset", type="float", default=0.85, min=0.0, max=1.0),
        Param(name="sigma", type="float", default=6.0, min=0.1, max=50.0),
    ),
    lines=(LineSpec(key="alma", label="ALMA {period}"),),
    render=Render(pane="price", style="line"),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["period"])),
    compute=lambda s, p: {
        "alma": kernel.alma(s.close, int(p["period"]), float(p["offset"]), float(p["sigma"]))
    },
)

_LSMA = IndicatorSpec(
    id="lsma",
    name="Least Squares Moving Average",
    group="averages",
    aliases=("Linear Regression Moving Average",),
    params=(Param(name="period", type="int", default=20, min=3, max=5000),),
    lines=(LineSpec(key="lsma", label="LSMA {period}"),),
    render=Render(pane="price", style="line"),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["period"])),
    compute=lambda s, p: {"lsma": kernel.linreg(s.close, int(p["period"]))},
)


AVERAGES: tuple[IndicatorSpec, ...] = (
    _SMA,
    _EMA,
    _WMA,
    _RMA,
    _HMA,
    _KAMA,
    _ALMA,
    _LSMA,
)
