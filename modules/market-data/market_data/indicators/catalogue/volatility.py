"""How much a bar moved, and where its close sat inside that move.

Three families that share `_safe_divide` and read the same OHLC: the ATR pair, the six
normalised candle-geometry ratios, and the OHLC volatility estimators — none of which
reads volume, because this archive has none worth reading
(docs/wskazniki-plan-wdrozenia.html, "Geometria świecy", "Zmienność z OHLC").
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from .. import kernel, warmup
from .arithmetic import LN2, safe_divide
from .spec import IndicatorSpec, Lines, LineSpec, Param, Render, Series, Warmup

_ATR = IndicatorSpec(
    id="atr",
    name="Average True Range",
    group="volatility",
    aliases=("Average True Range (Wilder)",),
    inputs=("high", "low", "close"),
    params=(Param(name="period", type="int", default=14, min=2, max=5000),),
    lines=(LineSpec(key="atr", label="ATR {period}"),),
    render=Render(pane="own", style="line", scale="own", autoscale=True),
    warmup=Warmup(kind="decay", bars=lambda p: warmup.rma_warmup_bars(int(p["period"]))),
    computer=Lines(lambda s, p: {
        "atr": kernel.rma(kernel.true_range(s.high, s.low, s.close), int(p["period"]))
    }),
)

_ATR_PCT = IndicatorSpec(
    id="atr_pct",
    name="Average True Range %",
    group="volatility",
    inputs=("high", "low", "close"),
    params=(Param(name="period", type="int", default=14, min=2, max=5000),),
    lines=(LineSpec(key="atr_pct", label="ATR% {period}"),),
    render=Render(pane="own", style="line", scale="own", autoscale=True),
    warmup=Warmup(kind="decay", bars=lambda p: warmup.rma_warmup_bars(int(p["period"]))),
    computer=Lines(lambda s, p: {
        "atr_pct": 100
        * safe_divide(
            kernel.rma(kernel.true_range(s.high, s.low, s.close), int(p["period"])), s.close
        )
    }),
)

# --- candle geometry: six numbers every candlestick pattern and every "reaction
# at a level" is built from, normalised so they compare across candles and
# instruments (docs/wskazniki-plan-wdrozenia.html, "Geometria świecy"). ---

_BAR_RANGE_ATR = IndicatorSpec(
    id="bar_range_atr",
    name="Bar Range in ATR",
    group="geometry",
    aliases=("Bar Range / ATR",),
    inputs=("high", "low", "close"),
    params=(Param(name="atr_period", type="int", default=14, min=2, max=5000),),
    lines=(LineSpec(key="bar_range_atr", label="Bar Range/ATR {atr_period}"),),
    render=Render(pane="own", style="line", scale="own", autoscale=True),
    warmup=Warmup(kind="decay", bars=lambda p: warmup.rma_warmup_bars(int(p["atr_period"]))),
    computer=Lines(lambda s, p: {
        "bar_range_atr": safe_divide(
            s.high - s.low,
            kernel.rma(kernel.true_range(s.high, s.low, s.close), int(p["atr_period"])),
        )
    }),
)

_BODY_RATIO = IndicatorSpec(
    id="body_ratio",
    name="Body Ratio",
    group="geometry",
    inputs=("open", "high", "low", "close"),
    lines=(LineSpec(key="body_ratio", label="Body Ratio"),),
    render=Render(pane="own", style="line", scale="fixed", range=(0.0, 1.0), autoscale=False),
    warmup=Warmup(kind="fixed", bars=lambda p: 0),
    computer=Lines(lambda s, p: {"body_ratio": safe_divide(np.abs(s.close - s.open), s.high - s.low)}),
)

_WICK_UP_RATIO = IndicatorSpec(
    id="wick_up_ratio",
    name="Upper Wick Ratio",
    group="geometry",
    inputs=("open", "high", "low", "close"),
    lines=(LineSpec(key="wick_up_ratio", label="Upper Wick Ratio"),),
    render=Render(pane="own", style="line", scale="fixed", range=(0.0, 1.0), autoscale=False),
    warmup=Warmup(kind="fixed", bars=lambda p: 0),
    computer=Lines(lambda s, p: {
        "wick_up_ratio": safe_divide(s.high - np.maximum(s.open, s.close), s.high - s.low)
    }),
)

_WICK_DOWN_RATIO = IndicatorSpec(
    id="wick_down_ratio",
    name="Lower Wick Ratio",
    group="geometry",
    inputs=("open", "high", "low", "close"),
    lines=(LineSpec(key="wick_down_ratio", label="Lower Wick Ratio"),),
    render=Render(pane="own", style="line", scale="fixed", range=(0.0, 1.0), autoscale=False),
    warmup=Warmup(kind="fixed", bars=lambda p: 0),
    computer=Lines(lambda s, p: {
        "wick_down_ratio": safe_divide(np.minimum(s.open, s.close) - s.low, s.high - s.low)
    }),
)

_CLOSE_POSITION = IndicatorSpec(
    id="close_position",
    name="Close Position",
    group="geometry",
    aliases=("Close Location Value",),
    inputs=("high", "low", "close"),
    lines=(LineSpec(key="close_position", label="Close Position"),),
    render=Render(pane="own", style="line", scale="fixed", range=(0.0, 1.0), autoscale=False),
    warmup=Warmup(kind="fixed", bars=lambda p: 0),
    computer=Lines(lambda s, p: {"close_position": safe_divide(s.close - s.low, s.high - s.low)}),
)

_GAP_PREV_CLOSE_ATR = IndicatorSpec(
    id="gap_prev_close_atr",
    name="Opening Gap in ATR",
    group="geometry",
    inputs=("open", "high", "low", "close"),
    params=(Param(name="atr_period", type="int", default=14, min=2, max=5000),),
    lines=(LineSpec(key="gap_prev_close_atr", label="Gap/ATR {atr_period}"),),
    render=Render(pane="own", style="line", scale="own", autoscale=True),
    warmup=Warmup(kind="decay", bars=lambda p: warmup.rma_warmup_bars(int(p["atr_period"]))),
    computer=Lines(lambda s, p: {
        "gap_prev_close_atr": safe_divide(
            s.open - kernel.shift(s.close, 1),
            kernel.rma(kernel.true_range(s.high, s.low, s.close), int(p["atr_period"])),
        )
    }),
)

# --- position in the range: where the close sits against its own recent history,
# without naming the halves "premium" or "discount" — that split is a threshold,
# a strategy's job, not a measure's (spec "Katalog mierzy, a nie orzeka"). ---

_RANGE_POSITION = IndicatorSpec(
    id="range_position",
    name="Range Position",
    group="range_position",
    inputs=("high", "low", "close"),
    params=(Param(name="period", type="int", default=20, min=2, max=5000),),
    lines=(LineSpec(key="range_position", label="Range Position {period}"),),
    render=Render(pane="own", style="line", scale="fixed", range=(0.0, 1.0), autoscale=False),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["period"])),
    computer=Lines(lambda s, p: {
        "range_position": safe_divide(
            s.close - kernel.rolling_min(s.low, int(p["period"])),
            kernel.rolling_max(s.high, int(p["period"])) - kernel.rolling_min(s.low, int(p["period"])),
        )
    }),
)

_ZSCORE = IndicatorSpec(
    id="zscore",
    name="Z-Score",
    group="range_position",
    params=(Param(name="period", type="int", default=20, min=2, max=5000),),
    lines=(LineSpec(key="zscore", label="Z-Score {period}"),),
    render=Render(pane="own", style="line", scale="own", autoscale=True),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["period"])),
    computer=Lines(lambda s, p: {
        "zscore": safe_divide(
            s.close - kernel.sma(s.close, int(p["period"])),
            kernel.stdev(s.close, int(p["period"])),
        )
    }),
)

# --- volatility from OHLC: a family with no volume in it at all, built for exactly
# the data this archive has (docs/wskazniki-plan-wdrozenia.html, "Zmienność z
# OHLC"). None of these annualise — the module has no trading calendar to
# annualise against (design.md, Ichimoku/Alligator decision) — so every one reads
# in the same per-bar log-return units as the others. ---

_STDEV = IndicatorSpec(
    id="stdev",
    name="Standard Deviation",
    group="volatility_estimators",
    params=(Param(name="period", type="int", default=20, min=2, max=5000),),
    lines=(LineSpec(key="stdev", label="StDev {period}"),),
    render=Render(pane="own", style="line", scale="own", autoscale=True),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["period"])),
    computer=Lines(lambda s, p: {"stdev": kernel.stdev(s.close, int(p["period"]))}),
)


def _compute_parkinson(s: Series, p: Mapping[str, float]) -> dict[str, np.ndarray]:
    period = int(p["period"])
    log_hl_sq = np.log(s.high / s.low) ** 2
    variance = kernel.sma(log_hl_sq, period) / (4 * LN2)
    return {"parkinson": np.sqrt(np.clip(variance, 0, None))}


_PARKINSON = IndicatorSpec(
    id="parkinson",
    name="Parkinson Volatility",
    group="volatility_estimators",
    inputs=("high", "low"),
    params=(Param(name="period", type="int", default=20, min=2, max=5000),),
    lines=(LineSpec(key="parkinson", label="Parkinson {period}"),),
    render=Render(pane="own", style="line", scale="own", autoscale=True),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["period"])),
    computer=Lines(_compute_parkinson),
)


def _compute_garman_klass(s: Series, p: Mapping[str, float]) -> dict[str, np.ndarray]:
    period = int(p["period"])
    per_bar = 0.5 * np.log(s.high / s.low) ** 2 - (2 * LN2 - 1) * np.log(s.close / s.open) ** 2
    variance = kernel.sma(per_bar, period)
    return {"garman_klass": np.sqrt(np.clip(variance, 0, None))}


_GARMAN_KLASS = IndicatorSpec(
    id="garman_klass",
    name="Garman-Klass Volatility",
    group="volatility_estimators",
    inputs=("open", "high", "low", "close"),
    params=(Param(name="period", type="int", default=20, min=2, max=5000),),
    lines=(LineSpec(key="garman_klass", label="Garman-Klass {period}"),),
    render=Render(pane="own", style="line", scale="own", autoscale=True),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["period"])),
    computer=Lines(_compute_garman_klass),
)


def _compute_rogers_satchell(s: Series, p: Mapping[str, float]) -> dict[str, np.ndarray]:
    period = int(p["period"])
    per_bar = np.log(s.high / s.close) * np.log(s.high / s.open) + np.log(s.low / s.close) * np.log(
        s.low / s.open
    )
    variance = kernel.sma(per_bar, period)
    return {"rogers_satchell": np.sqrt(np.clip(variance, 0, None))}


_ROGERS_SATCHELL = IndicatorSpec(
    id="rogers_satchell",
    name="Rogers-Satchell Volatility",
    group="volatility_estimators",
    inputs=("open", "high", "low", "close"),
    params=(Param(name="period", type="int", default=20, min=2, max=5000),),
    lines=(LineSpec(key="rogers_satchell", label="Rogers-Satchell {period}"),),
    render=Render(pane="own", style="line", scale="own", autoscale=True),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["period"])),
    computer=Lines(_compute_rogers_satchell),
)


def _compute_yang_zhang(s: Series, p: Mapping[str, float]) -> dict[str, np.ndarray]:
    period = int(p["period"])
    prev_close = kernel.shift(s.close, 1)
    overnight = np.log(safe_divide(s.open, prev_close))
    open_to_close = np.log(s.close / s.open)
    rs_per_bar = np.log(s.high / s.close) * np.log(s.high / s.open) + np.log(s.low / s.close) * np.log(
        s.low / s.open
    )

    k = 0.34 / (1.34 + (period + 1) / (period - 1))
    overnight_var = kernel.stdev(overnight, period, ddof=1) ** 2
    open_close_var = kernel.stdev(open_to_close, period, ddof=1) ** 2
    rs_var = kernel.sma(rs_per_bar, period)

    variance = overnight_var + k * open_close_var + (1 - k) * rs_var
    return {"yang_zhang": np.sqrt(np.clip(variance, 0, None))}


_YANG_ZHANG = IndicatorSpec(
    id="yang_zhang",
    name="Yang-Zhang Volatility",
    group="volatility_estimators",
    inputs=("open", "high", "low", "close"),
    params=(Param(name="period", type="int", default=20, min=2, max=5000),),
    lines=(LineSpec(key="yang_zhang", label="Yang-Zhang {period}"),),
    render=Render(pane="own", style="line", scale="own", autoscale=True),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["period"]) + 1),
    computer=Lines(_compute_yang_zhang),
)


def _compute_ulcer(s: Series, p: Mapping[str, float]) -> dict[str, np.ndarray]:
    period = int(p["period"])
    highest_close = kernel.rolling_max(s.close, period)
    drawdown_pct = 100 * safe_divide(s.close - highest_close, highest_close)
    return {"ulcer": np.sqrt(kernel.sma(drawdown_pct**2, period))}


_ULCER = IndicatorSpec(
    id="ulcer",
    name="Ulcer Index",
    group="volatility_estimators",
    params=(Param(name="period", type="int", default=14, min=2, max=5000),),
    lines=(LineSpec(key="ulcer", label="Ulcer {period}"),),
    render=Render(pane="own", style="line", scale="own", autoscale=True),
    # Doubly rolling — the highest-close window, then the mean-square-drawdown
    # window on top of it — so it needs two window's worth of history, the same
    # "sum of consecutive windows" rule `stoch` (oscillators.py) and `hma`
    # (averages.py) use too.
    warmup=Warmup(kind="fixed", bars=lambda p: 2 * int(p["period"])),
    computer=Lines(_compute_ulcer),
)


VOLATILITY: tuple[IndicatorSpec, ...] = (
    _ATR,
    _ATR_PCT,
    _BAR_RANGE_ATR,
    _BODY_RATIO,
    _WICK_UP_RATIO,
    _WICK_DOWN_RATIO,
    _CLOSE_POSITION,
    _GAP_PREV_CLOSE_ATR,
    _RANGE_POSITION,
    _ZSCORE,
    _STDEV,
    _PARKINSON,
    _GARMAN_KLASS,
    _ROGERS_SATCHELL,
    _YANG_ZHANG,
    _ULCER,
)
