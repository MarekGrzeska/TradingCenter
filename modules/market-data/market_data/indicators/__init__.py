"""Indicators techniczne, computed on the series this module already owns.

`kernel.py` is the math and nothing else — no FastAPI, no asyncpg, no pydantic, so that
moving it to a process of its own one day is moving a file, not rewriting one. `warmup.py`
turns a filter's decay into how many bars of history to read before trusting its answer.
`catalogue.py` is the published list: what an indicator is called, what it takes, what shape
it answers in, how to draw it — and the one thing none of the three ever produce is a
verdict. See `market-data-indicators` spec, "Katalog mierzy, a nie orzeka".
"""

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
