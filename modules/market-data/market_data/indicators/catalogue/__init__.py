"""What can be asked for, and how to compute it — one entry per indicator, which is the whole
contract with `GET /indicators`. Split by group, so another oscillator touches one file."""

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
    ClusterLevels,
    ComputeFn,
    Computer,
    HtfLevel,
    HtfLevels,
    HtfLevelsFn,
    IndicatorSpec,
    Lines,
    LineSpec,
    MarkerComputeFn,
    MarkerPoint,
    Markers,
    MinuteZoneFn,
    MinuteZones,
    Param,
    ParamOutOfRange,
    ProfileLevel,
    Render,
    Series,
    TimeProfile,
    TimeProfileFn,
    Warmup,
    Zone,
    ZoneComputeFn,
    Zones,
)
from .structure import STRUCTURE
from .volatility import VOLATILITY
from .zones import ZONES

# Bumped whenever a formula in this package changes — never when an entry is only added. Carried
# in the catalogue and in every computed response.
ALGORITHM_VERSION = 1

# Ordered as it is meant to be offered, which is why it is written out rather than collected by
# walking the package: the picker lists entries in this order, and a directory listing is not one.
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
    "ClusterLevels",
    "ComputeFn",
    "Computer",
    "HtfLevel",
    "HtfLevels",
    "HtfLevelsFn",
    "IndicatorSpec",
    "LineSpec",
    "Lines",
    "MarkerComputeFn",
    "MarkerPoint",
    "Markers",
    "MinuteZoneFn",
    "MinuteZones",
    "Param",
    "ParamOutOfRange",
    "ProfileLevel",
    "Render",
    "Series",
    "TimeProfile",
    "TimeProfileFn",
    "UnknownIndicator",
    "Warmup",
    "Zone",
    "ZoneComputeFn",
    "Zones",
    "all_entries",
    "get",
]
