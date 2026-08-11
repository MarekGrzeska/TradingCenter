"""What can be asked for, and how to compute it — one entry per indicator.

An entry is the whole contract between this module and everyone reading `GET
/indicators`: id, parameters, the shape it answers in, how to draw it, and the function
that produces it. A consumer never needs to know an indicator by name to offer it — it
reads this list (`market-data-indicators` spec, "Katalog wystarcza do zbudowania
wybieraka").

A package rather than one file, and the split is by group, not by output shape: adding
another oscillator touches `oscillators.py` and nothing else — not this file, not
`spec.py`, not the router, not the terminal. `spec.py` holds the entry shape, every other
module holds entries of it, and this one only orders them.

Kept separate from `kernel.py` on purpose: these modules know about parameters, defaults
and render hints, which are publishing concerns the kernel has no business with. They
stay free of FastAPI and asyncpg too, same as the kernel.
"""

from __future__ import annotations

from collections.abc import Sequence

from .averages import AVERAGES
from .bands import BANDS
from .oscillators import OSCILLATORS
from .profile import PROFILE
from .regime import REGIME
from .spec import (
    ClusterComputeFn,
    ClusterLevel,
    ComputeFn,
    HtfLevel,
    HtfLevelsFn,
    IndicatorSpec,
    LineSpec,
    MarkerComputeFn,
    MarkerPoint,
    MinuteZoneFn,
    Param,
    ParamOutOfRange,
    ProfileLevel,
    Render,
    Series,
    TimeProfileFn,
    Warmup,
    Zone,
    ZoneComputeFn,
)
from .structure import STRUCTURE
from .volatility import VOLATILITY
from .zones import ZONES

# Bumped whenever a formula in this package changes — never when an entry is only added.
# Carried in the catalogue and in every computed response (`market-data-indicators` spec,
# "Zmiana wzoru jest widoczna w odpowiedzi").
ALGORITHM_VERSION = 1

# Ordered as it is meant to be offered — averages first, since `sma` and `ema` are the
# entries every future indicator in that group will sit beside. Group order is the whole
# reason this tuple is written out rather than collected by walking the package: the
# picker lists entries in exactly this order, and a directory listing is not an order
# anyone chose.
CATALOGUE: tuple[IndicatorSpec, ...] = (
    *AVERAGES,
    *VOLATILITY,
    *REGIME,
    *OSCILLATORS,
    *BANDS,
    *STRUCTURE,
    *ZONES,
    *PROFILE,
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


__all__ = [
    "ALGORITHM_VERSION",
    "CATALOGUE",
    "ClusterComputeFn",
    "ClusterLevel",
    "ComputeFn",
    "HtfLevel",
    "HtfLevelsFn",
    "IndicatorSpec",
    "LineSpec",
    "MarkerComputeFn",
    "MarkerPoint",
    "MinuteZoneFn",
    "Param",
    "ParamOutOfRange",
    "ProfileLevel",
    "Render",
    "Series",
    "TimeProfileFn",
    "UnknownIndicator",
    "Warmup",
    "Zone",
    "ZoneComputeFn",
    "all_entries",
    "get",
]
