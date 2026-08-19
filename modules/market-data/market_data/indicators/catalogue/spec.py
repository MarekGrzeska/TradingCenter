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


# --- what an entry computes, and therefore what shape it answers with ----------------
#
# One field, seven cases. It used to be seven optional `compute_*` fields plus an
# `output` string declared beside them, and the two could disagree: an entry could
# announce `output="levels"` and set no level computer, or set `compute_zones` and leave
# `output` at its `"lines"` default. Neither is a state anything refused — the router
# picked a branch by asking which fields happened to be set, in an order that was itself
# the tie-break, and the wire published whatever the string said.
#
# `output` is derived from the case below rather than declared next to it, so the two can
# no longer disagree, and the router matches on the case instead of interrogating eight
# fields for `None`. The one thing this cannot express is an entry with two computers,
# which was never a thing an entry could usefully be.


@dataclass(frozen=True)
class Lines:
    """The ordinary case: one array per declared line, indexed by bar."""

    fn: ComputeFn


@dataclass(frozen=True)
class Markers:
    """Discrete events on the entry's own series — `swing_points`."""

    fn: MarkerComputeFn


@dataclass(frozen=True)
class ClusterLevels:
    """Price levels computed from the entry's own series — `level_clusters`."""

    fn: ClusterComputeFn


@dataclass(frozen=True)
class HtfLevels:
    """Price levels implied by one closed candle of a *coarser* resolution —
    `pivots_*`, `htf_levels_*`. The resolution belongs to the computer, not to the
    entry: it is the only case that reads a series other than the one requested from
    above, and the router reads it to know which one to fetch."""

    fn: HtfLevelsFn
    resolution: Resolution


@dataclass(frozen=True)
class Zones:
    """Regions on the entry's own series — `range_gap`, `body_gap`."""

    fn: ZoneComputeFn


@dataclass(frozen=True)
class MinuteZones:
    """Regions computed from the archive's fine series regardless of what resolution
    was requested — `session_range_*`, `opening_range`."""

    fn: MinuteZoneFn


@dataclass(frozen=True)
class TimeProfile:
    """Price buckets over the archive's fine series — `time_profile`."""

    fn: TimeProfileFn


Computer = Lines | Markers | ClusterLevels | HtfLevels | Zones | MinuteZones | TimeProfile

_OUTPUT_OF: dict[type, Literal["lines", "markers", "zones", "levels"]] = {
    Lines: "lines",
    Markers: "markers",
    ClusterLevels: "levels",
    HtfLevels: "levels",
    Zones: "zones",
    MinuteZones: "zones",
    TimeProfile: "levels",
}


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
    lines: tuple[LineSpec, ...] = ()
    render: Render = field(default_factory=lambda: Render(pane="price", style="line"))
    warmup: Warmup = field(default_factory=lambda: Warmup(kind="fixed", bars=lambda p: 0))
    computer: Computer = field(default_factory=lambda: Lines(lambda series, params: {}))

    @property
    def output(self) -> Literal["lines", "markers", "zones", "levels"]:
        """The shape this entry answers with, as published in the catalogue. Read off
        the computer, so it cannot be set to something the computer will not produce."""
        return _OUTPUT_OF[type(self.computer)]

    @property
    def higher_resolution(self) -> Resolution | None:
        """The coarser series this entry reads instead of the requested one, if any."""
        return self.computer.resolution if isinstance(self.computer, HtfLevels) else None

    @property
    def needs_minute_series(self) -> bool:
        """Whether this entry reads the archive's fine series regardless of what
        resolution was requested — which the router has to know before it reads
        anything."""
        return isinstance(self.computer, MinuteZones | TimeProfile)

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
