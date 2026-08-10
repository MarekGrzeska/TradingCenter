"""What can be asked for, and how to compute it — one entry per wskaźnik.

An entry is the whole contract between this module and everyone reading `GET
/indicators`: id, parameters, the shape it answers in, how to draw it, and the function
that produces it. A consumer never needs to know a wskaźnik by name to offer it — it reads
this list (`market-data-indicators` spec, "Katalog wystarcza do zbudowania wybieraka").

Kept separate from `kernel.py` on purpose: this file knows about parameters, defaults and
render hints, which is publishing concerns the kernel has no business with. It stays free
of FastAPI and asyncpg too, same as the kernel — a plain Python structure that the router
translates onto the wire.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from . import kernel, warmup

# Bumped whenever a formula in this module changes — never when an entry is only added.
# Carried in the catalogue and in every computed response (`market-data-indicators` spec,
# "Zmiana wzoru jest widoczna w odpowiedzi").
ALGORITHM_VERSION = 1


@dataclass(frozen=True)
class Series:
    """One pair's OHLC, aligned by bar index — what a `compute` function reads."""

    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray

    def __len__(self) -> int:
        return len(self.close)


@dataclass(frozen=True)
class Param:
    name: str
    type: Literal["int", "float"]
    default: float
    min: float
    max: float

    def clamp_or_raise(self, value: float) -> float:
        if not self.min <= value <= self.max:
            raise ParamOutOfRange(self.name, value, self.min, self.max)
        return value


class ParamOutOfRange(ValueError):
    def __init__(self, name: str, value: float, minimum: float, maximum: float) -> None:
        self.name = name
        self.value = value
        self.minimum = minimum
        self.maximum = maximum
        super().__init__(
            f"parameter {name!r} = {value!r} is outside [{minimum!r}, {maximum!r}]"
        )


@dataclass(frozen=True)
class LineSpec:
    key: str
    label: str


@dataclass(frozen=True)
class Render:
    pane: Literal["price", "own"]
    style: Literal["line", "dots", "histogram"]
    scale: Literal["price", "own", "fixed"] = "price"
    # Whether this wskaźnik's own values may widen the price axis it shares. A long
    # average sitting far from the current price would otherwise flatten the candles it
    # is drawn over (docs/wskazniki-plan-wdrozenia.html, pułapka 1).
    autoscale: bool = True
    range: tuple[float, float] | None = None
    levels: tuple[float, ...] = ()


@dataclass(frozen=True)
class Warmup:
    kind: Literal["fixed", "decay"]
    # Given the resolved parameters (already validated), how many bars of history this
    # entry needs read before the requested range for its answer to be trustworthy.
    bars: Callable[[Mapping[str, float]], int]


ComputeFn = Callable[[Series, Mapping[str, float]], dict[str, np.ndarray]]


@dataclass(frozen=True)
class IndicatorSpec:
    id: str
    name: str
    group: str
    # Names an operator might search by that are not the identifier — never the
    # identifier itself, so the two lists cannot say the same thing twice.
    aliases: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ("close",)
    params: tuple[Param, ...] = ()
    output: Literal["lines", "markers", "zones", "levels"] = "lines"
    lines: tuple[LineSpec, ...] = ()
    render: Render = field(default_factory=lambda: Render(pane="price", style="line"))
    warmup: Warmup = field(default_factory=lambda: Warmup(kind="fixed", bars=lambda p: 0))
    compute: ComputeFn = field(default=lambda series, params: {})

    def resolve_params(self, requested: Mapping[str, float]) -> dict[str, float]:
        """Requested values over defaults, each checked against its declared range.

        Unknown keys in `requested` are ignored rather than refused: a client sending a
        parameter this entry does not have is not this entry's problem to police.
        """
        resolved: dict[str, float] = {}
        for param in self.params:
            value = requested.get(param.name, param.default)
            resolved[param.name] = param.clamp_or_raise(float(value))
        return resolved

    def warmup_bars(self, resolved_params: Mapping[str, float]) -> int:
        return self.warmup.bars(resolved_params)


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
    compute=lambda s, p: {
        "atr": kernel.rma(kernel.true_range(s.high, s.low, s.close), int(p["period"]))
    },
)

def _safe_divide(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    """`numerator / denominator`, `np.nan` where undefined instead of a runtime
    warning — division by a zero high-low range or a flat window is a property of
    the data (a single-tick candle, an illiquid pair), not a bug in the formula."""
    with np.errstate(invalid="ignore", divide="ignore"):
        return numerator / denominator


_LN2 = float(np.log(2.0))


_ATR_PCT = IndicatorSpec(
    id="atr_pct",
    name="Average True Range %",
    group="volatility",
    inputs=("high", "low", "close"),
    params=(Param(name="period", type="int", default=14, min=2, max=5000),),
    lines=(LineSpec(key="atr_pct", label="ATR% {period}"),),
    render=Render(pane="own", style="line", scale="own", autoscale=True),
    warmup=Warmup(kind="decay", bars=lambda p: warmup.rma_warmup_bars(int(p["period"]))),
    compute=lambda s, p: {
        "atr_pct": 100
        * _safe_divide(
            kernel.rma(kernel.true_range(s.high, s.low, s.close), int(p["period"])), s.close
        )
    },
)

# --- geometria świecy: six numbers every candlestick pattern and every "reaction
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
    compute=lambda s, p: {
        "bar_range_atr": _safe_divide(
            s.high - s.low,
            kernel.rma(kernel.true_range(s.high, s.low, s.close), int(p["atr_period"])),
        )
    },
)

_BODY_RATIO = IndicatorSpec(
    id="body_ratio",
    name="Body Ratio",
    group="geometry",
    inputs=("open", "high", "low", "close"),
    lines=(LineSpec(key="body_ratio", label="Body Ratio"),),
    render=Render(pane="own", style="line", scale="fixed", range=(0.0, 1.0), autoscale=False),
    warmup=Warmup(kind="fixed", bars=lambda p: 0),
    compute=lambda s, p: {"body_ratio": _safe_divide(np.abs(s.close - s.open), s.high - s.low)},
)

_WICK_UP_RATIO = IndicatorSpec(
    id="wick_up_ratio",
    name="Upper Wick Ratio",
    group="geometry",
    inputs=("open", "high", "low", "close"),
    lines=(LineSpec(key="wick_up_ratio", label="Upper Wick Ratio"),),
    render=Render(pane="own", style="line", scale="fixed", range=(0.0, 1.0), autoscale=False),
    warmup=Warmup(kind="fixed", bars=lambda p: 0),
    compute=lambda s, p: {
        "wick_up_ratio": _safe_divide(s.high - np.maximum(s.open, s.close), s.high - s.low)
    },
)

_WICK_DOWN_RATIO = IndicatorSpec(
    id="wick_down_ratio",
    name="Lower Wick Ratio",
    group="geometry",
    inputs=("open", "high", "low", "close"),
    lines=(LineSpec(key="wick_down_ratio", label="Lower Wick Ratio"),),
    render=Render(pane="own", style="line", scale="fixed", range=(0.0, 1.0), autoscale=False),
    warmup=Warmup(kind="fixed", bars=lambda p: 0),
    compute=lambda s, p: {
        "wick_down_ratio": _safe_divide(np.minimum(s.open, s.close) - s.low, s.high - s.low)
    },
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
    compute=lambda s, p: {"close_position": _safe_divide(s.close - s.low, s.high - s.low)},
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
    compute=lambda s, p: {
        "gap_prev_close_atr": _safe_divide(
            s.open - kernel.shift(s.close, 1),
            kernel.rma(kernel.true_range(s.high, s.low, s.close), int(p["atr_period"])),
        )
    },
)

# --- położenie w zakresie: where the close sits against its own recent history,
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
    compute=lambda s, p: {
        "range_position": _safe_divide(
            s.close - kernel.rolling_min(s.low, int(p["period"])),
            kernel.rolling_max(s.high, int(p["period"])) - kernel.rolling_min(s.low, int(p["period"])),
        )
    },
)

_ZSCORE = IndicatorSpec(
    id="zscore",
    name="Z-Score",
    group="range_position",
    params=(Param(name="period", type="int", default=20, min=2, max=5000),),
    lines=(LineSpec(key="zscore", label="Z-Score {period}"),),
    render=Render(pane="own", style="line", scale="own", autoscale=True),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["period"])),
    compute=lambda s, p: {
        "zscore": _safe_divide(
            s.close - kernel.sma(s.close, int(p["period"])),
            kernel.stdev(s.close, int(p["period"])),
        )
    },
)

# --- zmienność z OHLC: a family with no volume in it at all, built for exactly
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
    compute=lambda s, p: {"stdev": kernel.stdev(s.close, int(p["period"]))},
)


def _compute_parkinson(s: Series, p: Mapping[str, float]) -> dict[str, np.ndarray]:
    period = int(p["period"])
    log_hl_sq = np.log(s.high / s.low) ** 2
    variance = kernel.sma(log_hl_sq, period) / (4 * _LN2)
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
    compute=_compute_parkinson,
)


def _compute_garman_klass(s: Series, p: Mapping[str, float]) -> dict[str, np.ndarray]:
    period = int(p["period"])
    per_bar = 0.5 * np.log(s.high / s.low) ** 2 - (2 * _LN2 - 1) * np.log(s.close / s.open) ** 2
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
    compute=_compute_garman_klass,
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
    compute=_compute_rogers_satchell,
)


def _compute_yang_zhang(s: Series, p: Mapping[str, float]) -> dict[str, np.ndarray]:
    period = int(p["period"])
    prev_close = kernel.shift(s.close, 1)
    overnight = np.log(_safe_divide(s.open, prev_close))
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
    compute=_compute_yang_zhang,
)


def _compute_ulcer(s: Series, p: Mapping[str, float]) -> dict[str, np.ndarray]:
    period = int(p["period"])
    highest_close = kernel.rolling_max(s.close, period)
    drawdown_pct = 100 * _safe_divide(s.close - highest_close, highest_close)
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
    # "sum of consecutive windows" rule `stoch` and `hma` use below.
    warmup=Warmup(kind="fixed", bars=lambda p: 2 * int(p["period"])),
    compute=_compute_ulcer,
)

# --- reżim: whether there is a trend at all, the question none of the geometry
# above answers, and the one a "break of structure" needs an honest answer to
# before it means anything (docs/wskazniki-plan-wdrozenia.html, "Reżim"). ---


def _compute_adx(s: Series, p: Mapping[str, float]) -> dict[str, np.ndarray]:
    period = int(p["period"])
    up_move = np.diff(s.high, prepend=s.high[0])
    down_move = -np.diff(s.low, prepend=s.low[0])
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr_smoothed = kernel.rma(kernel.true_range(s.high, s.low, s.close), period)
    plus_di = 100 * _safe_divide(kernel.rma(plus_dm, period), tr_smoothed)
    minus_di = 100 * _safe_divide(kernel.rma(minus_dm, period), tr_smoothed)
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
    compute=_compute_adx,
)


def _compute_choppiness(s: Series, p: Mapping[str, float]) -> dict[str, np.ndarray]:
    period = int(p["period"])
    tr_sum = kernel.sma(kernel.true_range(s.high, s.low, s.close), period) * period
    range_hl = kernel.rolling_max(s.high, period) - kernel.rolling_min(s.low, period)
    ratio = _safe_divide(tr_sum, range_hl)
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
    compute=_compute_choppiness,
)


def _compute_aroon(s: Series, p: Mapping[str, float]) -> dict[str, np.ndarray]:
    period = int(p["period"])
    bars_since_high = kernel.rolling_argmax(s.high, period)
    bars_since_low = kernel.rolling_argmin(s.low, period)
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
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["period"])),
    compute=_compute_aroon,
)


def _compute_vortex(s: Series, p: Mapping[str, float]) -> dict[str, np.ndarray]:
    period = int(p["period"])
    prev_low = kernel.shift(s.low, 1)
    prev_high = kernel.shift(s.high, 1)
    vm_plus_sum = kernel.sma(np.abs(s.high - prev_low), period) * period
    vm_minus_sum = kernel.sma(np.abs(s.low - prev_high), period) * period
    tr_sum = kernel.sma(kernel.true_range(s.high, s.low, s.close), period) * period
    return {
        "vi_plus": _safe_divide(vm_plus_sum, tr_sum),
        "vi_minus": _safe_divide(vm_minus_sum, tr_sum),
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
    compute=_compute_vortex,
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
    compute=lambda s, p: {"linreg_slope": kernel.linreg_slope(s.close, int(p["period"]))},
)

_R_SQUARED = IndicatorSpec(
    id="r_squared",
    name="R-Squared",
    group="regime",
    params=(Param(name="period", type="int", default=14, min=3, max=5000),),
    lines=(LineSpec(key="r_squared", label="R² {period}"),),
    render=Render(pane="own", style="line", scale="fixed", range=(0.0, 1.0), autoscale=False),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["period"])),
    compute=lambda s, p: {"r_squared": kernel.r_squared(s.close, int(p["period"]))},
)

# --- średnie: bias and reference point, cheap because every one of them comes
# from the same primitives (docs/wskazniki-plan-wdrozenia.html, "Średnie"). `sma`
# and `ema` are already in the catalogue from etap zero. ---

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

# Ordered as it is meant to be offered — averages first, since `sma` and `ema` are the
# entries every future wskaźnik in this group will sit beside.
CATALOGUE: tuple[IndicatorSpec, ...] = (
    _SMA,
    _EMA,
    _WMA,
    _RMA,
    _HMA,
    _KAMA,
    _ALMA,
    _LSMA,
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
    _ADX,
    _CHOPPINESS,
    _AROON,
    _VORTEX,
    _LINREG_SLOPE,
    _R_SQUARED,
)

_BY_ID: dict[str, IndicatorSpec] = {entry.id: entry for entry in CATALOGUE}


class UnknownIndicator(KeyError):
    def __init__(self, indicator_id: str) -> None:
        self.indicator_id = indicator_id
        super().__init__(f"no indicator named {indicator_id!r}")


def get(indicator_id: str) -> IndicatorSpec:
    try:
        return _BY_ID[indicator_id]
    except KeyError:
        raise UnknownIndicator(indicator_id) from None


def all_entries() -> Sequence[IndicatorSpec]:
    return CATALOGUE
