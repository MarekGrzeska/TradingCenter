"""Everything one run reads from the archive, gathered before it computes: each series it needs from the warm-up before
the range to its end, each indicator line on its series' bars, and what the archive could not vouch for. Read in pieces
the archive accepts — its indicator ceiling is candles × indicators per request."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np

from .archive import Archive
from .document import Checked
from .requirements import IndicatorKey, Needs, needs
from .series import PERIOD_SECONDS, Context, Series, epoch
from .vocabulary import Indicator

# Bars per request: under the archive's 200 000 candles × indicators, with one indicator per request.
CHUNK_BARS = 100_000


@dataclass(frozen=True)
class Inputs:
    series: dict[Context, Series]
    indicators: dict[IndicatorKey, np.ndarray]
    uncovered: dict[Context, list[tuple[int, int]]]
    needs: Needs
    read_from: int

    def fingerprints(self) -> dict[str, Any]:
        return {f"{symbol}@{resolution}": s.fingerprint() for (symbol, resolution), s in sorted(self.series.items())}


def minute_bars(range_from: int, range_to: int) -> int:
    """The most minute candles a range can hold — what the run's ceiling is measured in, known before anything is read."""
    return max(0, (range_to - range_from) // 60)


async def read(
    archive: Archive,
    checked: Checked,
    params: Mapping[str, float],
    catalogue: Mapping[str, Indicator],
    range_from: int,
    range_to: int,
) -> Inputs:
    required = needs(checked, params, catalogue)
    start = range_from - required.warmup_seconds
    series: dict[Context, Series] = {}
    uncovered: dict[Context, list[tuple[int, int]]] = {}
    for context in sorted(required.contexts):
        rows: list[dict[str, Any]] = []
        gaps: list[tuple[int, int]] = []
        for lo, hi in _pieces(start, range_to, context[1]):
            answer = await archive.candles(context[0], context[1], _moment(lo), _moment(hi))
            rows.extend(answer["candles"])
            gaps.extend((epoch(u["from"]), epoch(u["to"])) for u in answer.get("uncovered", []))
        series[context] = Series.from_candles(context[1], rows)
        uncovered[context] = [(max(a, range_from), b) for a, b in gaps if b > range_from]

    indicators: dict[IndicatorKey, np.ndarray] = {}
    for key in sorted(required.indicators, key=repr):
        target = series[key.context]
        values = np.full(len(target), np.nan)
        position = {int(s): i for i, s in enumerate(target.starts.tolist())}
        for lo, hi in _pieces(start, range_to, key.context[1]):
            answer = await archive.indicator(
                key.context[0], key.context[1], _moment(lo), _moment(hi), key.id, dict(key.params)
            )
            line = answer["lines"].get(key.line) or []
            for moment, value in zip(answer["times"], line, strict=False):
                index = position.get(epoch(moment))
                if index is not None and value is not None:
                    values[index] = float(value)
        indicators[key] = values
    return Inputs(series, indicators, uncovered, required, start)


def _pieces(start: int, end: int, resolution: str) -> list[tuple[int, int]]:
    width = CHUNK_BARS * PERIOD_SECONDS[resolution]
    return [(lo, min(lo + width, end)) for lo in range(start, end, width)]


def _moment(seconds: int) -> datetime:
    return datetime.fromtimestamp(seconds, tz=UTC)
