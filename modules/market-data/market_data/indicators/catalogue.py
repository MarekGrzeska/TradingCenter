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

# Ordered as it is meant to be offered — averages first, since `sma` and `ema` are the
# entries every future wskaźnik in this group will sit beside.
CATALOGUE: tuple[IndicatorSpec, ...] = (_SMA, _EMA, _ATR)

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
