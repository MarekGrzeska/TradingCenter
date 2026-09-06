"""Reaching one kind of computer off a catalogue entry, in a test. `IndicatorSpec.computer` is a
tagged union, so a test says which kind it means and fails with the entry's name if the shape changed."""

from __future__ import annotations

from typing import Any

from market_data.indicators.catalogue import CATALOGUE, IndicatorSpec, Lines

# Every entry that answers with lines — the only ones a `compute(series, params)` test has anything
# to say about. The rest are exercised by the file named after their group.
LINE_ENTRIES: list[IndicatorSpec] = [e for e in CATALOGUE if isinstance(e.computer, Lines)]


def fn_of(entry: IndicatorSpec, kind: type) -> Any:
    computer = entry.computer
    assert isinstance(computer, kind), (
        f"{entry.id} computes {type(computer).__name__}, not {kind.__name__}"
    )
    return computer.fn
