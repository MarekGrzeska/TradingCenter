"""What became of a setup: the bars after it, walked under three rules that are each the pessimistic reading. A
backtest that flatters itself is worse than none, because it is believed."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from ..spec import Candle, Decision
from .costs import CostModel

Ending = Literal["target", "stop", "timeout"]


@dataclass(frozen=True)
class Outcome:
    """One setup, resolved. `r` is the whole point: money is instrument-specific, risk is
    not, so every metric downstream is in multiples of what was risked."""

    opened_at: datetime
    closed_at: datetime
    direction: str
    entry: float
    stop: float
    target: float
    exit: float
    ending: Ending
    r: float
    bars_held: int
    features: dict[str, float]

    @property
    def won(self) -> bool:
        return self.r > 0


def resolve(
    decision: Decision,
    *,
    opened_at: datetime,
    following: Sequence[Candle],
    costs: CostModel,
) -> Outcome | None:
    """Walk the bars after a setup until the stop or the target is touched. `None` when there are no bars
    after it at all — that is not a timeout and must not be counted as one."""
    if decision.action != "trade" or not following:
        return None
    assert decision.direction is not None
    assert decision.entry is not None and decision.stop is not None and decision.target is not None

    direction = decision.direction
    entry = costs.entry_price(decision.entry, direction)
    stop, target = decision.stop, decision.target
    # Risk is measured from the price actually paid, not from the one the strategy hoped
    # for: the cost of entering is part of what is at risk.
    risk = abs(entry - stop)
    if risk <= 0:
        return None

    for index, candle in enumerate(following, start=1):
        hit_stop = candle.low <= stop if direction == "long" else candle.high >= stop
        hit_target = candle.high >= target if direction == "long" else candle.low <= target
        if hit_stop or hit_target:
            # Both in one bar: the stop. The candle says both prices traded and not in
            # which order, and guessing the kind one is how a backtest flatters itself.
            ending: Ending = "stop" if hit_stop else "target"
            raw = stop if hit_stop else target
            return _outcome(decision, opened_at, candle, index, entry, raw, risk, ending, costs)

    last = following[-1]
    return _outcome(
        decision, opened_at, last, len(following), entry, last.close, risk, "timeout", costs
    )


def _outcome(
    decision: Decision,
    opened_at: datetime,
    candle: Candle,
    bars: int,
    entry: float,
    raw_exit: float,
    risk: float,
    ending: Ending,
    costs: CostModel,
) -> Outcome:
    direction = decision.direction or "long"
    exit_price = costs.exit_price(raw_exit, direction)
    moved = (exit_price - entry) if direction == "long" else (entry - exit_price)
    return Outcome(
        opened_at=opened_at,
        closed_at=candle.time,
        direction=direction,
        entry=entry,
        stop=decision.stop or 0.0,
        target=decision.target or 0.0,
        exit=exit_price,
        ending=ending,
        r=moved / risk - costs.commission_r,
        bars_held=bars,
        features=dict(decision.features),
    )


def apply_daily_stop(outcomes: Sequence[Outcome], *, limit_r: float | None) -> list[Outcome]:
    """Drop the setups a daily loss budget would have stopped anybody taking. Here rather than beside the
    live gates: a daily budget counts realised results, and live there is nothing to count."""
    if limit_r is None:
        return list(outcomes)
    kept: list[Outcome] = []
    spent: dict[object, float] = {}
    for outcome in sorted(outcomes, key=lambda item: item.opened_at):
        day = outcome.opened_at.date()
        if spent.get(day, 0.0) <= -abs(limit_r):
            continue
        kept.append(outcome)
        spent[day] = spent.get(day, 0.0) + min(outcome.r, 0.0)
    return kept
