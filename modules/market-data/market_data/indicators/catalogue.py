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

# Ordered as it is meant to be offered — averages first, since `sma` and `ema` are the
# entries every future wskaźnik in this group will sit beside.
CATALOGUE: tuple[IndicatorSpec, ...] = (
    _SMA,
    _EMA,
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
