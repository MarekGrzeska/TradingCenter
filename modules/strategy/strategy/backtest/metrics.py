"""What a run came to, in R rather than in money, because money is instrument-specific and risk is not. Splitting the
trades at each feature's median is the crudest honest answer to which part of a bundle carries the edge."""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from .simulate import Outcome


@dataclass(frozen=True)
class Metrics:
    trades: int
    wins: int
    win_rate: float
    expectancy_r: float = field(metadata={"unit": "R per trade"})
    total_r: float = 0.0
    profit_factor: float | None = None
    max_drawdown_r: float = 0.0
    longest_losing_streak: int = 0
    average_bars_held: float = 0.0
    # How many setups the range produced but never resolved — they sat at its edge. Named rather than
    # folded in, because a run whose trades are mostly these has not measured what it looks like.
    unresolved: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FeatureSplit:
    """One feature, read as two halves of the same population."""

    feature: str
    median: float
    low_half_expectancy_r: float
    high_half_expectancy_r: float
    low_half_trades: int
    high_half_trades: int

    @property
    def separation_r(self) -> float:
        """How much the feature tells apart. Near zero means it carries nothing."""
        return self.high_half_expectancy_r - self.low_half_expectancy_r

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "separation_r": self.separation_r}


def measure(outcomes: Sequence[Outcome], *, unresolved: int = 0) -> Metrics:
    if not outcomes:
        return Metrics(
            trades=0, wins=0, win_rate=0.0, expectancy_r=0.0, unresolved=unresolved
        )

    results = [outcome.r for outcome in outcomes]
    wins = [value for value in results if value > 0]
    losses = [value for value in results if value <= 0]
    gross_loss = abs(sum(losses))

    return Metrics(
        trades=len(results),
        wins=len(wins),
        win_rate=len(wins) / len(results),
        expectancy_r=statistics.fmean(results),
        total_r=sum(results),
        # `None` rather than infinity when nothing was lost: a run with no losing trade has
        # no ratio, and printing `inf` invites reading it as a very good one.
        profit_factor=(sum(wins) / gross_loss) if gross_loss else None,
        max_drawdown_r=_max_drawdown(results),
        longest_losing_streak=_longest_losing_streak(results),
        average_bars_held=statistics.fmean([o.bars_held for o in outcomes]),
        unresolved=unresolved,
    )


def _max_drawdown(results: Sequence[float]) -> float:
    """The deepest fall from a peak of the running total, in R — the number that decides whether a
    strategy is survivable, and the one an operator has to accept before starting."""
    peak = running = 0.0
    worst = 0.0
    for value in results:
        running += value
        peak = max(peak, running)
        worst = min(worst, running - peak)
    return worst


def _longest_losing_streak(results: Sequence[float]) -> int:
    longest = current = 0
    for value in results:
        current = current + 1 if value <= 0 else 0
        longest = max(longest, current)
    return longest


def attribute(outcomes: Sequence[Outcome], *, minimum_per_half: int = 5) -> list[FeatureSplit]:
    """Which of a strategy's own features tell its good trades from its bad ones. A feature is reported
    only when both halves hold enough trades; the floor is low, because the alternative is reporting nothing."""
    names = sorted({name for outcome in outcomes for name in outcome.features})
    splits: list[FeatureSplit] = []
    for name in names:
        present = [outcome for outcome in outcomes if name in outcome.features]
        if len(present) < minimum_per_half * 2:
            continue
        median = statistics.median(outcome.features[name] for outcome in present)
        low = [outcome.r for outcome in present if outcome.features[name] <= median]
        high = [outcome.r for outcome in present if outcome.features[name] > median]
        if len(low) < minimum_per_half or len(high) < minimum_per_half:
            # Every value on one side of its own median — a feature that was constant, or
            # nearly. Nothing to tell apart.
            continue
        splits.append(
            FeatureSplit(
                feature=name,
                median=median,
                low_half_expectancy_r=statistics.fmean(low),
                high_half_expectancy_r=statistics.fmean(high),
                low_half_trades=len(low),
                high_half_trades=len(high),
            )
        )
    return sorted(splits, key=lambda split: abs(split.separation_r), reverse=True)
