"""What can be asked for, and how to compute it — one entry per indicator.

An entry is the whole contract between this module and everyone reading `GET
/indicators`: id, parameters, the shape it answers in, how to draw it, and the function
that produces it. A consumer never needs to know an indicator by name to offer it — it reads
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
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

import numpy as np

from ..models import Resolution
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
    # Overrides the entry's own `render.style` for this one line — MACD's
    # histogram line inside an otherwise line-style entry, and the only reason
    # this field exists. `None` means: use the entry's `render.style`.
    style: Literal["line", "dots", "histogram"] | None = None


@dataclass(frozen=True)
class Render:
    pane: Literal["price", "own"]
    style: Literal["line", "dots", "histogram"]
    scale: Literal["price", "own", "fixed"] = "price"
    # Whether this indicator's own values may widen the price axis it shares. A long
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
class MarkerPoint:
    """One `markers`-shaped event, indexed the same way `compute`'s arrays are —
    the router turns `bar` into a timestamp once it knows which axis it computed
    against, the same trimming `[first_requested:]` already does for lines."""

    bar: int
    label: str
    price: float | None = None


MarkerComputeFn = Callable[[Series, Mapping[str, float]], list[MarkerPoint]]


@dataclass(frozen=True)
class ClusterLevel:
    """One `levels`-shaped entry computed from this entry's own series — as
    opposed to `HtfLevel`, which comes from a different resolution entirely."""

    bar: int
    price: float
    label: str
    count: int


ClusterComputeFn = Callable[[Series, Mapping[str, float]], list[ClusterLevel]]


@dataclass(frozen=True)
class HtfLevel:
    """One price level implied by a single closed higher-resolution candle —
    `pivots_*` and `htf_levels_*`. No `bar`: the candle this is computed from
    belongs to a different series than the one the request asked to draw over,
    so the router places it in time itself, from the candle it read."""

    price: float
    label: str


HtfLevelsFn = Callable[[tuple[float, float, float, float]], list[HtfLevel]]


@dataclass(frozen=True)
class Zone:
    """One `zones`-shaped region, indexed the same way `compute`'s arrays are —
    a gap between three consecutive bars, a session window, an opening range.
    `end_bar` is `None` while the zone has not closed within the read range,
    `IndicatorZoneOut.to`'s own null meaning carried one level down."""

    start_bar: int
    end_bar: int | None
    top: float
    bottom: float
    direction: Literal["bullish", "bearish"] | None = None
    touched_at_bar: int | None = None
    filled_at_bar: int | None = None


# `session_close_before[i]` is true when the archive has *verified* there is no
# candle between bar `i - 1` and bar `i` — a confirmed market closure, not merely
# an unverified stretch (`coverage.py`'s `Absence.MARKET_CLOSED` vs
# `NOT_COLLECTED`). Computed once per request in the router from data it already
# reads for the top-level `uncovered` field, and handed to whichever zone
# entries read it — the kernel still never touches asyncpg itself (task 4.3).
ZoneComputeFn = Callable[[Series, Mapping[str, float], np.ndarray], list[Zone]]

# A second `zones` pipeline, for entries that read the archive's own MINUTE
# series regardless of what resolution was requested (`session_range`,
# `opening_range`) — the same "read a different series than the one being drawn
# over" shape `HtfLevelsFn` already uses for pivots, just finer instead of
# coarser. `times` are that minute series' own instants — a bucket has no price
# to derive a calendar day or a local hour from, unlike every `ComputeFn` above.
MinuteZoneFn = Callable[[Series, Sequence[datetime], Mapping[str, float]], list[Zone]]


@dataclass(frozen=True)
class ProfileLevel:
    """One price-bucket row of a `levels`-shaped time-profile entry. No `bar`:
    a bucket is not indexed against any bar axis, the same reason `HtfLevel`
    has none — the router places every row at one shared moment, the start of
    the requested range."""

    price: float
    label: str | None
    count: int | None


TimeProfileFn = Callable[[Series, Sequence[datetime], Mapping[str, float]], list[ProfileLevel]]


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
    # Set instead of `compute` for an `output="markers"` entry.
    compute_markers: MarkerComputeFn | None = None
    # Set instead of `compute` for an `output="levels"` entry computed from this
    # entry's own series, e.g. `level_clusters`.
    compute_cluster_levels: ClusterComputeFn | None = None
    # Set together with `higher_resolution` for an `output="levels"` entry computed
    # from one closed candle of a *different* resolution, e.g. `pivots_classic`.
    higher_resolution: Resolution | None = None
    compute_htf_levels: HtfLevelsFn | None = None
    # Set instead of `compute` for an `output="zones"` entry computed from this
    # entry's own series — `range_gap`, `body_gap`.
    compute_zones: ZoneComputeFn | None = None
    # `compute_minute_zones` and `compute_time_profile` both read the archive's
    # MINUTE series instead of whatever resolution was requested — set together
    # with `needs_minute_series`, which tells the router to fetch it.
    needs_minute_series: bool = False
    compute_minute_zones: MinuteZoneFn | None = None
    compute_time_profile: TimeProfileFn | None = None

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

# --- regime: whether there is a trend at all, the question none of the geometry
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

# --- averages: bias and reference point, cheap because every one of them comes
# from the same primitives (docs/wskazniki-plan-wdrozenia.html, "Średnie"). `sma`
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

# --- oscillators: mostly for divergence-hunting and for the non-SMC strategies,
# cheap because they are all built from finished primitives
# (docs/wskazniki-plan-wdrozenia.html, "Oscylatory"). ---


def _rsi_values(close: np.ndarray, period: int) -> np.ndarray:
    change = kernel.diff(close, 1)
    # Bar 0 has no earlier bar to change from — read as "0 change", not "unknown
    # change", the same reasoning `_compute_adx` documents: `rma` seeds
    # recursively from index 0, and a NaN seed poisons every bar after it.
    no_prior_bar = np.isnan(change)
    gains = np.where(no_prior_bar, 0.0, np.maximum(change, 0.0))
    losses = np.where(no_prior_bar, 0.0, np.maximum(-change, 0.0))
    rs = _safe_divide(kernel.rma(gains, period), kernel.rma(losses, period))
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
    compute=lambda s, p: {"rsi": _rsi_values(s.close, int(p["period"]))},
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
    # The slow EMA's own decay, plus the signal EMA's decay stacked on top of it —
    # the same two-stage-recursion reasoning as `adx`'s warmup, since `signal` is
    # an `ema` of a series that already contains an unstabilised `ema`.
    warmup=Warmup(
        kind="decay",
        bars=lambda p: warmup.ema_warmup_bars(int(p["slow_period"]))
        + warmup.ema_warmup_bars(int(p["signal_period"])),
    ),
    compute=_compute_macd,
)


def _compute_stoch(s: Series, p: Mapping[str, float]) -> dict[str, np.ndarray]:
    k_period = int(p["k_period"])
    lowest = kernel.rolling_min(s.low, k_period)
    highest = kernel.rolling_max(s.high, k_period)
    raw_k = 100 * _safe_divide(s.close - lowest, highest - lowest)
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
    compute=_compute_stoch,
)


def _compute_stoch_rsi(s: Series, p: Mapping[str, float]) -> dict[str, np.ndarray]:
    rsi = _rsi_values(s.close, int(p["rsi_period"]))
    stoch_period = int(p["stoch_period"])
    lowest = kernel.rolling_min(rsi, stoch_period)
    highest = kernel.rolling_max(rsi, stoch_period)
    raw_k = 100 * _safe_divide(rsi - lowest, highest - lowest)
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
    compute=_compute_stoch_rsi,
)


def _compute_cci(s: Series, p: Mapping[str, float]) -> dict[str, np.ndarray]:
    period = int(p["period"])
    typical = (s.high + s.low + s.close) / 3
    deviation = 0.015 * kernel.mean_abs_dev(typical, period)
    return {"cci": _safe_divide(typical - kernel.sma(typical, period), deviation)}


_CCI = IndicatorSpec(
    id="cci",
    name="Commodity Channel Index",
    group="oscillators",
    inputs=("high", "low", "close"),
    params=(Param(name="period", type="int", default=20, min=2, max=5000),),
    lines=(LineSpec(key="cci", label="CCI {period}"),),
    render=Render(pane="own", style="line", scale="own", autoscale=True),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["period"])),
    compute=_compute_cci,
)

_ROC = IndicatorSpec(
    id="roc",
    name="Rate of Change",
    group="oscillators",
    params=(Param(name="period", type="int", default=9, min=1, max=5000),),
    lines=(LineSpec(key="roc", label="ROC {period}"),),
    render=Render(pane="own", style="line", scale="own", autoscale=True),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["period"])),
    compute=lambda s, p: {
        "roc": 100
        * _safe_divide(
            s.close - kernel.shift(s.close, int(p["period"])), kernel.shift(s.close, int(p["period"]))
        )
    },
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
    compute=lambda s, p: {
        "williams_r": -100
        * _safe_divide(
            kernel.rolling_max(s.high, int(p["period"])) - s.close,
            kernel.rolling_max(s.high, int(p["period"])) - kernel.rolling_min(s.low, int(p["period"])),
        )
    },
)


def _compute_cmo(s: Series, p: Mapping[str, float]) -> dict[str, np.ndarray]:
    period = int(p["period"])
    change = kernel.diff(s.close, 1)
    no_prior_bar = np.isnan(change)
    gains = np.where(no_prior_bar, 0.0, np.maximum(change, 0.0))
    losses = np.where(no_prior_bar, 0.0, np.maximum(-change, 0.0))
    sum_gain = kernel.sma(gains, period) * period
    sum_loss = kernel.sma(losses, period) * period
    return {"cmo": 100 * _safe_divide(sum_gain - sum_loss, sum_gain + sum_loss)}


_CMO = IndicatorSpec(
    id="cmo",
    name="Chande Momentum Oscillator",
    group="oscillators",
    params=(Param(name="period", type="int", default=9, min=2, max=5000),),
    lines=(LineSpec(key="cmo", label="CMO {period}"),),
    render=Render(pane="own", style="line", scale="fixed", range=(-100.0, 100.0), autoscale=False),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["period"])),
    compute=_compute_cmo,
)

# --- bands and channels: donchian is also "where the last n bars' extremes sit" —
# the same number serving two very different purposes
# (docs/wskazniki-plan-wdrozenia.html, "Wstęgi i kanały"). ---


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
    return {"percent_b": _safe_divide(s.close - lower, upper - lower)}


_BBANDS_PERCENT_B = IndicatorSpec(
    id="bbands_percent_b",
    name="Bollinger %B",
    group="bands",
    params=(
        Param(name="period", type="int", default=20, min=2, max=5000),
        Param(name="mult", type="float", default=2.0, min=0.1, max=10.0),
    ),
    lines=(LineSpec(key="percent_b", label="%B {period}"),),
    # Not pinned to [0, 1] like the ratios in "candle geometry" — a price outside
    # its own bands is exactly what this line exists to show, and a fixed scale
    # would clip that off screen.
    render=Render(pane="own", style="line", scale="own", autoscale=True, levels=(0.0, 1.0)),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["period"])),
    compute=_compute_bbands_percent_b,
)


def _compute_bbands_bandwidth(s: Series, p: Mapping[str, float]) -> dict[str, np.ndarray]:
    upper, basis, lower = _bbands_edges(s, p)
    return {"bandwidth": _safe_divide(upper - lower, basis)}


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

# --- points and levels: rare events and reference lines, still with no
# interpretation on top (docs/wskazniki-plan-wdrozenia.html, "W1 — punkty i poziomy").
# `n` here is the one decision the whole group shares — how many bars on each
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
    output="markers",
    render=Render(pane="price", style="dots"),
    warmup=Warmup(kind="fixed", bars=lambda p: int(p["n"])),
    compute_markers=_compute_swing_points,
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
    compute=_compute_last_swing_high,
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
    compute=_compute_last_swing_low,
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
    compute=lambda s, p: {
        "upper": kernel.rolling_max(s.high, int(p["n"])),
        "lower": kernel.rolling_min(s.low, int(p["n"])),
    },
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
    output="levels",
    render=Render(pane="price", style="line"),
    warmup=Warmup(kind="fixed", bars=lambda p: max(int(p["n"]), int(p["atr_period"]))),
    compute_cluster_levels=_compute_level_clusters,
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
    output="levels",
    render=Render(pane="price", style="line"),
    warmup=Warmup(kind="fixed", bars=lambda p: 0),
    higher_resolution=Resolution.DAY,
    compute_htf_levels=lambda ohlc: _htf_ohlc_levels(ohlc, "PD"),
)

_HTF_LEVELS_WEEK = IndicatorSpec(
    id="htf_levels_week",
    name="Previous Week Levels",
    group="structure",
    aliases=("PWH/PWL",),
    inputs=("open", "high", "low", "close"),
    output="levels",
    render=Render(pane="price", style="line"),
    warmup=Warmup(kind="fixed", bars=lambda p: 0),
    higher_resolution=Resolution.WEEK,
    compute_htf_levels=lambda ohlc: _htf_ohlc_levels(ohlc, "PW"),
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
        output="levels",
        render=Render(pane="price", style="line"),
        warmup=Warmup(kind="fixed", bars=lambda p: 0),
        higher_resolution=Resolution.DAY,
        compute_htf_levels=fn,
    )
    for id_, name, fn in _PIVOT_TYPES
)

# --- zones: three-bar imbalances and fixed clock windows, all sharing the same
# `zones` shape — a region with a top, a bottom and a moment it took effect,
# open on the right until something closes it (docs/wskazniki-plan-wdrozenia.html,
# "W2 — strefy"). No market calendar backs any of this: `session_range` and
# `opening_range` take their window as parameters rather than looking one up,
# the same non-goal design.md's Ichimoku/Alligator decision already recorded
# ("market_status wie tylko, czy rynek jest otwarty teraz"). ---


def _three_bar_gaps(
    hi: np.ndarray,
    lo: np.ndarray,
    session_close_before: np.ndarray,
    skip_session_gaps: bool,
) -> list[Zone]:
    """A void between bar `i - 1` and bar `i + 1` that bar `i` itself never
    reaches into, in whichever direction `i`'s impulse moved — the "fair value
    gap" a three-bar pattern is, on whichever pair of edges the caller hands in
    (`hi`/`lo` are the full wick range for `range_gap`, the body's own edges for
    `body_gap`; the pattern itself does not care which).

    Touched and filled are different claims: touched is price merely reaching
    the near edge again, filled is a later bar crossing all the way to the far
    one. Only the second means the imbalance is gone, so only the second closes
    the zone (`end_bar`) — `IndicatorZoneOut.to` stays null on a merely-touched
    gap, same as one nothing has come back to at all.

    A candidate spanning a confirmed market closure (`session_close_before`) is
    skipped when `skip_session_gaps` is set — a weekend is not an imbalance,
    task 4.3's whole point.
    """
    n = len(hi)
    zones: list[Zone] = []
    for i in range(1, n - 1):
        if skip_session_gaps and (session_close_before[i] or session_close_before[i + 1]):
            continue
        direction: Literal["bullish", "bearish"]
        if lo[i + 1] > hi[i - 1]:
            top, bottom, direction = float(lo[i + 1]), float(hi[i - 1]), "bullish"
        elif hi[i + 1] < lo[i - 1]:
            top, bottom, direction = float(lo[i - 1]), float(hi[i + 1]), "bearish"
        else:
            continue

        touched_at: int | None = None
        filled_at: int | None = None
        # `i + 2`, not `i + 1`: bar `i + 1` is one of the three bars that forms
        # the gap in the first place (its own edge *is* `top`, by construction
        # above), so starting the scan there would count the gap as touching
        # itself the instant it exists.
        for j in range(i + 2, n):
            if direction == "bullish":
                if touched_at is None and lo[j] <= top:
                    touched_at = j
                if lo[j] <= bottom:
                    filled_at = j
                    break
            else:
                if touched_at is None and hi[j] >= bottom:
                    touched_at = j
                if hi[j] >= top:
                    filled_at = j
                    break

        zones.append(
            Zone(
                start_bar=i - 1,
                end_bar=filled_at,
                top=top,
                bottom=bottom,
                direction=direction,
                touched_at_bar=touched_at,
                filled_at_bar=filled_at,
            )
        )
    return zones


def _body_edges(s: Series) -> tuple[np.ndarray, np.ndarray]:
    return np.maximum(s.open, s.close), np.minimum(s.open, s.close)


_SKIP_SESSION_GAPS_PARAM = Param(name="skip_session_gaps", type="int", default=1, min=0, max=1)

_RANGE_GAP = IndicatorSpec(
    id="range_gap",
    name="Range Gap",
    group="zones",
    aliases=("Fair Value Gap", "FVG", "Imbalance"),
    inputs=("high", "low"),
    params=(_SKIP_SESSION_GAPS_PARAM,),
    output="zones",
    render=Render(pane="price", style="line"),
    warmup=Warmup(kind="fixed", bars=lambda p: 0),
    compute_zones=lambda s, p, session_close_before: _three_bar_gaps(
        s.high, s.low, session_close_before, bool(p["skip_session_gaps"])
    ),
)

_BODY_GAP = IndicatorSpec(
    id="body_gap",
    name="Body Gap",
    group="zones",
    inputs=("open", "close"),
    params=(_SKIP_SESSION_GAPS_PARAM,),
    output="zones",
    render=Render(pane="price", style="line"),
    warmup=Warmup(kind="fixed", bars=lambda p: 0),
    compute_zones=lambda s, p, session_close_before: _three_bar_gaps(
        *_body_edges(s), session_close_before, bool(p["skip_session_gaps"])
    ),
)


def _fixed_window_zones(
    s: Series, days: Sequence[object], in_window: Callable[[int], bool]
) -> list[Zone]:
    """Groups consecutive in-window minute bars into one zone apiece — shared
    by `_session_window_zones` (a window per local calendar day) and
    `_opening_range_zones` (a window per UTC calendar day), which differ only
    in how `in_window` decides a bar belongs to today's window, and in which
    calendar `days` names.

    A day boundary always closes whatever window was open first, even if
    `in_window` would call the new day's own first bar "inside" too — a
    window defined in its own zone's local hours never legitimately reaches
    midnight, so two different days' windows must never merge into one zone
    just because nothing out-of-window separated them.
    """
    zones: list[Zone] = []
    window_bars: list[int] = []

    def flush(closed: bool) -> None:
        if not window_bars:
            return
        highs = [float(s.high[b]) for b in window_bars]
        lows = [float(s.low[b]) for b in window_bars]
        zones.append(
            Zone(
                start_bar=window_bars[0],
                end_bar=window_bars[-1] if closed else None,
                top=max(highs),
                bottom=min(lows),
            )
        )
        window_bars.clear()

    for i in range(len(days)):
        if i > 0 and days[i] != days[i - 1]:
            flush(closed=True)
        if in_window(i):
            window_bars.append(i)
        else:
            flush(closed=True)
    # Whatever is still open when the read range ends has not closed within it
    # — `end_bar=None`, `IndicatorZoneOut.to`'s null, same as an unfilled gap.
    flush(closed=False)
    return zones


def _session_window_zones(zone_info: ZoneInfo) -> MinuteZoneFn:
    """One zone per local calendar day in `zone_info`, spanning the bars whose
    local clock time falls in `[from_hour, to_hour)` — a fixed window, not a
    market-hours lookup (see the "zones" section banner above). `zoneinfo`
    resolves the UTC offset per calendar day rather than once for the whole
    read, so the same local hours line up across a DST change instead of
    sliding by the transition's hour (task 4.9)."""

    def compute(s: Series, times: Sequence[datetime], p: Mapping[str, float]) -> list[Zone]:
        from_hour = float(p["from_hour"])
        to_hour = float(p["to_hour"])
        local_times = [t.astimezone(zone_info) for t in times]
        days = [t.date() for t in local_times]

        def in_window(i: int) -> bool:
            local = local_times[i]
            hour = local.hour + local.minute / 60 + local.second / 3600
            return from_hour <= hour < to_hour

        return _fixed_window_zones(s, days, in_window)

    return compute


def _opening_range_zones(s: Series, times: Sequence[datetime], p: Mapping[str, float]) -> list[Zone]:
    """The high-low range of the first `window_minutes` of each UTC calendar
    day — `htf_levels_day` anchors to the same boundary for the same reason:
    it is the only "day" this module can name without a session calendar
    (design.md, Ichimoku/Alligator decision). Kept to the most recent `n` —
    unlike a gap or a session window, nothing bounds how many opening ranges a
    wide daily-chart request would otherwise produce."""
    window = timedelta(minutes=int(p["window_minutes"]))
    n = int(p["n"])
    days = [t.date() for t in times]
    day_starts = [t.replace(hour=0, minute=0, second=0, microsecond=0) for t in times]

    def in_window(i: int) -> bool:
        return times[i] < day_starts[i] + window

    zones = _fixed_window_zones(s, days, in_window)
    return zones[-n:] if n > 0 else []


_SESSION_TYPES: tuple[tuple[str, str, str, float, float], ...] = (
    ("session_range_london", "London Session Range", "Europe/London", 8.0, 16.5),
    ("session_range_new_york", "New York Session Range", "America/New_York", 9.5, 16.0),
    ("session_range_tokyo", "Tokyo Session Range", "Asia/Tokyo", 9.0, 15.0),
)

_SESSIONS: tuple[IndicatorSpec, ...] = tuple(
    IndicatorSpec(
        id=id_,
        name=name,
        group="zones",
        inputs=("high", "low"),
        params=(
            Param(name="from_hour", type="float", default=default_from, min=0.0, max=24.0),
            Param(name="to_hour", type="float", default=default_to, min=0.0, max=24.0),
        ),
        output="zones",
        render=Render(pane="price", style="line"),
        warmup=Warmup(kind="fixed", bars=lambda p: 0),
        needs_minute_series=True,
        compute_minute_zones=_session_window_zones(ZoneInfo(tz_name)),
    )
    for id_, name, tz_name, default_from, default_to in _SESSION_TYPES
)

_OPENING_RANGE = IndicatorSpec(
    id="opening_range",
    name="Opening Range",
    group="zones",
    aliases=("ORB", "Opening Range Breakout"),
    inputs=("high", "low"),
    params=(
        Param(name="window_minutes", type="int", default=30, min=1, max=240),
        Param(name="n", type="int", default=5, min=1, max=50),
    ),
    output="zones",
    render=Render(pane="price", style="line"),
    warmup=Warmup(kind="fixed", bars=lambda p: 0),
    needs_minute_series=True,
    compute_minute_zones=_opening_range_zones,
)

# --- time profile: how much of the read range's own time each price bucket
# held, from the MINUTE series regardless of what resolution is charted
# (docs/wskazniki-plan-wdrozenia.html, "W3 — profil czasowy"). No volume backs
# this archive (task 1.16's boundary), so "how much" is a count of one-minute
# bars, not traded size — a TPO profile's own convention, not a volume
# profile's. ---


def _time_profile_levels(
    s: Series, times: Sequence[datetime], p: Mapping[str, float]
) -> list[ProfileLevel]:
    """Buckets each minute bar by its typical price `(H+L+C)/3` into a bucket
    `bucket_atr` fractions of ATR wide — resolving design.md's open question in
    favour of an ATR fraction, the same unit `level_clusters`' tolerance
    already uses, over a fixed multiple of the instrument's own tick step this
    module has no per-instrument table for. One bar, one bucket: splitting a
    bar's own high-low range across every bucket it touches is a legitimate
    reading too, but this one is the one a hand recount of a small sample can
    actually check (task 5.5), which a fractional split cannot promise.

    The point of control is the single busiest bucket; the value area expands
    outward from it, always into whichever open neighbour currently holds
    more, until it covers `value_area_pct` of the bars read — the standard
    TPO rule, weighed by bar count in place of traded size.
    """
    n = len(s)
    if n == 0:
        return []

    atr_period = int(p["atr_period"])
    bucket_atr = float(p["bucket_atr"])
    value_area_pct = float(p["value_area_pct"])

    atr = kernel.rma(kernel.true_range(s.high, s.low, s.close), atr_period)
    reference_atr = float(atr[-1])
    bucket_width = bucket_atr * reference_atr
    if not bucket_width > 0:
        return []

    typical = (s.high + s.low + s.close) / 3
    lowest = float(np.min(s.low))
    bucket_of = np.floor((typical - lowest) / bucket_width).astype(np.int64)

    counts: dict[int, int] = {}
    for bucket in bucket_of:
        counts[int(bucket)] = counts.get(int(bucket), 0) + 1

    total = sum(counts.values())
    poc_bucket = max(counts, key=lambda b: (counts[b], -b))

    included_low = included_high = poc_bucket
    accumulated = counts[poc_bucket]
    target = total * value_area_pct / 100
    while accumulated < target:
        below, above = included_low - 1, included_high + 1
        gain_below, gain_above = counts.get(below, 0), counts.get(above, 0)
        if gain_below == 0 and gain_above == 0:
            break
        if gain_below >= gain_above:
            included_low, accumulated = below, accumulated + gain_below
        else:
            included_high, accumulated = above, accumulated + gain_above

    def price_of(bucket: int) -> float:
        return lowest + (bucket + 0.5) * bucket_width

    levels = [
        ProfileLevel(price=price_of(bucket), label="POC" if bucket == poc_bucket else None, count=count)
        for bucket, count in sorted(counts.items())
    ]
    levels.append(
        ProfileLevel(price=lowest + (included_high + 1) * bucket_width, label="VAH", count=None)
    )
    levels.append(ProfileLevel(price=lowest + included_low * bucket_width, label="VAL", count=None))
    return levels


_TIME_PROFILE = IndicatorSpec(
    id="time_profile",
    name="Time Profile",
    group="profile",
    aliases=("TPO Profile", "Market Profile"),
    inputs=("high", "low", "close"),
    params=(
        Param(name="atr_period", type="int", default=14, min=2, max=5000),
        Param(name="bucket_atr", type="float", default=0.25, min=0.01, max=5.0),
        Param(name="value_area_pct", type="float", default=70.0, min=1.0, max=99.9),
    ),
    output="levels",
    render=Render(pane="price", style="histogram"),
    warmup=Warmup(kind="fixed", bars=lambda p: 0),
    needs_minute_series=True,
    compute_time_profile=_time_profile_levels,
)

# Ordered as it is meant to be offered — averages first, since `sma` and `ema` are the
# entries every future indicator in this group will sit beside.
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
    _RSI,
    _MACD,
    _STOCH,
    _STOCH_RSI,
    _CCI,
    _ROC,
    _WILLIAMS_R,
    _CMO,
    _BBANDS,
    _BBANDS_PERCENT_B,
    _BBANDS_BANDWIDTH,
    _KELTNER,
    _DONCHIAN,
    _ENVELOPE,
    _SWING_POINTS,
    _LAST_SWING_HIGH,
    _LAST_SWING_LOW,
    _ROLLING_EXTREME,
    _LEVEL_CLUSTERS,
    _HTF_LEVELS_DAY,
    _HTF_LEVELS_WEEK,
    *_PIVOTS,
    _RANGE_GAP,
    _BODY_GAP,
    *_SESSIONS,
    _OPENING_RANGE,
    _TIME_PROFILE,
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
