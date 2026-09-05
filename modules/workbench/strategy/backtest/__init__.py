"""The backtest: history walked through the very function the loop calls. Everything `run` needs is in
this package or is the strategy's own; there is no second implementation of any rule."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from ..archive import Archive
from ..catalogue import get
from ..spec import StrategySpec
from .costs import FREE, CostModel
from .metrics import attribute, measure
from .replay import batch, candles_after, decide_at, incremental, slice_at
from .report import NotComparable, Report, compare
from .simulate import Outcome, apply_daily_stop, resolve

__all__ = [
    "FREE",
    "CostModel",
    "NotComparable",
    "Outcome",
    "Report",
    "attribute",
    "batch",
    "compare",
    "decide_at",
    "incremental",
    "measure",
    "resolve",
    "run",
    "slice_at",
]

# How many bars a setup is given to resolve before it is closed at the market. Long enough that a slow
# winner is not cut off, short enough that a forgotten position stops pretending to be an open trade.
RESOLUTION_LIMIT_BARS = 500


async def run(
    archive: Archive,
    strategy: str | StrategySpec,
    symbol: str,
    *,
    start: datetime,
    end: datetime,
    params: Mapping[str, float] | None = None,
    costs: CostModel = FREE,
    daily_loss_limit_r: float | None = None,
    revision: int | None = None,
    revision_id: int | None = None,
) -> Report:
    """One strategy over one range, with the costs stated. The read happens once and every bar is decided
    off it. An id names an entry in this image's catalogue, so a run of the reference needs no database."""
    spec = strategy if isinstance(strategy, StrategySpec) else get(strategy)
    resolved = spec.resolve_params(params)
    read = await archive.read_facts(spec, symbol, resolved, as_of=end, bars_from=start)

    decided = []
    for candle in read.facts.candles:
        if not (start <= candle.time <= end):
            continue
        replayed = decide_at(spec, resolved, read, candle.time, gaps=read.gaps)
        if replayed is not None:
            decided.append(replayed)

    refusals: dict[str, int] = {}
    outcomes: list[Outcome] = []
    unresolved = 0
    for replayed in decided:
        if replayed.decision.action != "trade":
            refusals[replayed.reason_kind] = refusals.get(replayed.reason_kind, 0) + 1
            continue
        outcome = resolve(
            replayed.decision,
            opened_at=replayed.as_of,
            following=candles_after(read, replayed.as_of, limit=RESOLUTION_LIMIT_BARS),
            costs=costs,
        )
        if outcome is None:
            unresolved += 1
        else:
            outcomes.append(outcome)

    kept = apply_daily_stop(outcomes, limit_r=daily_loss_limit_r)
    return Report(
        strategy_id=spec.id,
        strategy_revision=revision,
        strategy_revision_id=revision_id,
        symbol=symbol,
        resolution=spec.resolution,
        range_from=start,
        range_to=end,
        params=resolved,
        costs=costs,
        metrics=measure(kept, unresolved=unresolved),
        attribution=attribute(kept),
        bars=len(decided),
        refusals=refusals,
    )
