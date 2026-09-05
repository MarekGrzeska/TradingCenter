"""Technical indicators, computed on the series this module already owns. `kernel.py` is the maths
and nothing else; `catalogue/` is the published list — and none of it ever produces a verdict."""

from __future__ import annotations

from .catalogue import (
    ALGORITHM_VERSION,
    CATALOGUE,
    IndicatorSpec,
    ParamOutOfRange,
    UnknownIndicator,
)
from .catalogue import get as get_indicator

__all__ = [
    "ALGORITHM_VERSION",
    "CATALOGUE",
    "IndicatorSpec",
    "ParamOutOfRange",
    "UnknownIndicator",
    "get_indicator",
]
