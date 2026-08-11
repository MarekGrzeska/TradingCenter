"""The shape of a catalogue entry, and nothing that is one.

Every group module in this package builds `IndicatorSpec`s out of these types; the
package's `__init__` collects them into `CATALOGUE`. Split out so that adding another
average or another oscillator touches one group file and never this one — the entry
shape is a contract with the router and the terminal, the entries themselves are data.

Free of FastAPI and asyncpg, same as `kernel.py` — a plain Python structure the router
translates onto the wire.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

import numpy as np

from ...models import Resolution


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
