"""Everything one run reads from the archive, gathered before it computes: each series it needs from the warm-up before
the range to its end, each indicator line on its series' bars, and what the archive could not vouch for. Read in pieces
the archive accepts — its indicator ceiling is candles × indicators per request."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from .archive import Archive
from .document import Checked
from .requirements import IndicatorKey, Needs, needs
from .series import PERIOD_SECONDS, Context, Series, epoch, moment
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
    # Indicators the archive computed from less history than they want before the range (`settled: false`).
    unsettled: list[IndicatorKey]

    def fingerprints(self) -> dict[str, Any]:
        return {f"{symbol}@{resolution}": s.fingerprint() for (symbol, resolution), s in sorted(self.series.items())}


def execution_bars(range_from: int, range_to: int, resolution: str) -> int:
    """The most candles of the execution series a range can hold — what the run's ceiling is measured in, known before
    anything is read."""
    return max(0, (range_to - range_from) // PERIOD_SECONDS[resolution])


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
        first = start if context in required.warm else range_from
        for lo, hi in _pieces(first, range_to, context[1]):
            answer = await archive.candles(context[0], context[1], moment(lo), moment(hi))
            rows.extend(answer["candles"])
            gaps.extend((epoch(u["from"]), epoch(u["to"])) for u in answer.get("uncovered", []))
        # Off the loop: a year of minutes is half a million rows of parsing, and this process serves the stream.
        series[context] = await asyncio.to_thread(Series.from_candles, context[1], rows)
        uncovered[context] = [(max(a, range_from), b) for a, b in gaps if b > range_from]

    indicators: dict[IndicatorKey, np.ndarray] = {}
    unsettled: list[IndicatorKey] = []
    for key in sorted(required.indicators, key=repr):
        target = series[key.context]
        values = np.full(len(target), np.nan)
        settled = True
        for lo, hi in _pieces(start, range_to, key.context[1]):
            answer = await archive.indicator(
                key.context[0], key.context[1], moment(lo), moment(hi), key.id, dict(key.params)
            )
            settled = settled and answer["settled"]
            line = np.array([np.nan if v is None else float(v) for v in answer["lines"].get(key.line) or []])
            moments = np.array([epoch(m) for m in answer["times"][: len(line)]], dtype=np.int64)
            # Placed by period start on the series' own bars; a time the series does not have is dropped.
            index = np.searchsorted(target.starts, moments)
            hit = (index < len(target)) & (target.starts[np.clip(index, 0, len(target) - 1)] == moments)
            values[index[hit]] = line[hit]
        indicators[key] = values
        if not settled:
            unsettled.append(key)
    return Inputs(series, indicators, uncovered, required, start, unsettled)


def _pieces(start: int, end: int, resolution: str) -> list[tuple[int, int]]:
    width = CHUNK_BARS * PERIOD_SECONDS[resolution]
    return [(lo, min(lo + width, end)) for lo in range(start, end, width)]


def bars_without_minutes(decision: Series, minute: Series, range_from: int, range_to: int) -> str | None:
    """Why a run settled on minutes cannot be made over this range, or `None`: a decision bar with no minute inside it
    would leave an order or an exit waiting for the next minute there is, however many days later."""
    inside = np.flatnonzero((decision.starts >= range_from) & (decision.available <= range_to))
    starts = decision.starts[inside]
    ends = starts + PERIOD_SECONDS[decision.resolution]
    empty = np.searchsorted(minute.starts, ends) == np.searchsorted(minute.starts, starts)
    if not empty.any():
        return None
    holes: list[tuple[int, int]] = []
    previous = -2
    for i in np.flatnonzero(empty).tolist():
        if i == previous + 1:
            holes[-1] = (holes[-1][0], int(ends[i]))
        else:
            holes.append((int(starts[i]), int(ends[i])))
        previous = i
    listed = ", ".join(f"{_iso(a)} to {_iso(b)}" for a, b in holes[:3])
    within = minute.starts[(minute.starts >= range_from) & (minute.starts < range_to)]
    first = f"the archive's first minute in the range is {_iso(int(within[0]))}" if len(within) else (
        "the archive has no minute in the range"
    )
    return (
        f"{int(empty.sum())} of {len(inside)} {decision.resolution} bars in the range have no minute under them, and this "
        f"strategy's stops, targets or orders are settled on minutes — first gaps: {listed}; {first}. Nothing was computed"
    )


def _iso(seconds: int) -> str:
    return moment(seconds).strftime("%Y-%m-%d %H:%M UTC")
