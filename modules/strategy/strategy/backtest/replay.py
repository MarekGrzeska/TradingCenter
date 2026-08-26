"""History, walked bar by bar through the very function the loop calls. One `evaluate`, two drivers, and
there must never be a second implementation — the look-ahead test compares this module against itself.

Slicing is where look-ahead actually creeps in: a fact read over the whole range carries answers about
the future, and `slice_at` masks all of it. Getting that wrong is invisible in the equity curve."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from ..archive import Archive, FactsRead, Gap
from ..gates import ReasonKind, apply, coverage, reward_over_risk
from ..periods import period_length
from ..runner.loop import MINIMUM_REWARD_OVER_RISK
from ..spec import Candle, Decision, Facts, FactValue, StrategySpec

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Replayed:
    """One bar's decision, as the loop would have recorded it."""

    as_of: datetime
    decision: Decision
    reason_kind: ReasonKind


def slice_at(read: FactsRead, as_of: datetime, *, candles: int) -> Facts:
    """The facts as they would have looked at `as_of`, and nothing later. The subtle one is a zone's
    `touched_at`/`filled_at`: the zone existed, but what later became of it is exactly what must not leak."""
    kept_candles = tuple(candle for candle in read.facts.candles if candle.time <= as_of)
    values: dict[str, FactValue] = {}
    for key, value in read.facts.values.items():
        upto = sum(1 for stamp in value.times if stamp <= as_of)
        values[key] = FactValue(
            key=value.key,
            resolution=value.resolution,
            times=value.times[:upto],
            lines={name: series[:upto] for name, series in value.lines.items()},
            markers=tuple(marker for marker in value.markers if marker.time <= as_of),
            zones=tuple(
                _zone_as_of(zone, as_of) for zone in value.zones if zone.start <= as_of
            ),
            levels=tuple(level for level in value.levels if level.time <= as_of),
            error=value.error,
        )
    return Facts(
        symbol=read.facts.symbol,
        as_of=as_of,
        candles=kept_candles[-candles:],
        values=values,
    )


def _zone_as_of(zone, as_of: datetime):
    from ..spec import Zone

    return Zone(
        start=zone.start,
        end=zone.end if zone.end is not None and zone.end <= as_of else None,
        top=zone.top,
        bottom=zone.bottom,
        direction=zone.direction,
        touched_at=zone.touched_at
        if zone.touched_at is not None and zone.touched_at <= as_of
        else None,
        filled_at=zone.filled_at
        if zone.filled_at is not None and zone.filled_at <= as_of
        else None,
    )


def decide_at(
    spec: StrategySpec,
    params: Mapping[str, float],
    read: FactsRead,
    as_of: datetime,
    *,
    gaps: Sequence[Gap] = (),
) -> Replayed | None:
    """One bar, decided the way the loop decides it — the same gates in the same order. `None` when the
    bar has no candles behind it yet: warmup, not a decision."""
    facts = slice_at(read, as_of, candles=spec.candles)
    if not facts.candles:
        return None
    decision = spec.evaluate(facts, params)
    decision, kind = apply(
        decision,
        [coverage(gaps), reward_over_risk(decision, MINIMUM_REWARD_OVER_RISK)],
    )
    return Replayed(as_of=as_of, decision=decision, reason_kind=kind)


def _bars_in(read: FactsRead, start: datetime, end: datetime) -> list[datetime]:
    return [
        candle.time for candle in read.facts.candles if start <= candle.time <= end
    ]


async def batch(
    archive: Archive,
    spec: StrategySpec,
    symbol: str,
    params: Mapping[str, float],
    *,
    start: datetime,
    end: datetime,
) -> list[Replayed]:
    """The whole range read once, then walked — what a backtest actually runs. Over two years of hourly
    bars that is the difference between a request and seventeen thousand of them."""
    read = await archive.read_facts(spec, symbol, params, as_of=end, bars_from=start)
    decided = []
    for as_of in _bars_in(read, start, end):
        replayed = decide_at(spec, params, read, as_of, gaps=read.gaps)
        if replayed is not None:
            decided.append(replayed)
    return decided


async def incremental(
    archive: Archive,
    spec: StrategySpec,
    symbol: str,
    params: Mapping[str, float],
    *,
    start: datetime,
    end: datetime,
) -> list[Replayed]:
    """One read per bar, exactly as the loop would have done it. Slow by construction: it exists to be
    compared against `batch`, and a difference is look-ahead."""
    outline = await archive.read_facts(spec, symbol, params, as_of=end, bars_from=start)
    decided = []
    for as_of in _bars_in(outline, start, end):
        read = await archive.read_facts(spec, symbol, params, as_of=as_of)
        replayed = decide_at(spec, params, read, as_of, gaps=read.gaps)
        if replayed is not None:
            decided.append(replayed)
    return decided


def candles_after(read: FactsRead, as_of: datetime, *, limit: int) -> list[Candle]:
    """The bars a setup at `as_of` would have had to resolve in."""
    later = [candle for candle in read.facts.candles if candle.time > as_of]
    return later[:limit]


def range_bars(resolution: str, start: datetime, end: datetime) -> int:
    return max(int((end - start) / period_length(resolution)), 0) + 1
