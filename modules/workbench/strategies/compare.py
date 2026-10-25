"""Runs side by side, and only runs that can be: the same range, the same costs and the same engine, or the difference is
the comparison (`strategies-tools`). Nothing here says which run is better."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .runs import RunRow

# What a comparison lists of each run's report — the numbers a reader weighs, not the curve.
METRICS = (
    "trades", "win_rate", "expectancy_r", "total_r", "profit_factor", "max_drawdown_r", "max_drawdown_pct",
    "sharpe", "sortino", "calmar", "longest_losing_streak", "total_r_without_best_5", "pessimistic_resolutions",
)


class NotComparable(Exception):
    def __init__(self, reasons: list[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons


def compare(rows: Sequence[RunRow]) -> list[dict[str, Any]]:
    """Each run's revision, parameters and metrics, in the order asked. `NotComparable` names every reason they are not."""
    reasons = [f"run {r.id} is {r.status}, not done" for r in rows if r.status != "done" or r.report is None]
    if reasons:
        raise NotComparable(reasons)
    first = rows[0]
    for other in rows[1:]:
        if _range(other) != _range(first):
            reasons.append(f"run {other.id} covers {_range(other)}, run {first.id} {_range(first)}")
        if other.request["costs"] != first.request["costs"]:
            differing = sorted(
                key for key in {*other.request["costs"], *first.request["costs"]}
                if other.request["costs"].get(key) != first.request["costs"].get(key)
            )
            reasons.append(f"run {other.id} differs from run {first.id} in costs: {', '.join(differing)}")
        if other.engine_version != first.engine_version:
            reasons.append(
                f"run {other.id} was computed by engine {other.engine_version}, run {first.id} by {first.engine_version}"
            )
    if reasons:
        raise NotComparable(reasons)
    return [
        {
            "run_id": r.id, "strategy_id": r.strategy_id, "revision": r.revision, "params": r.request["params"],
            **{name: (r.report or {}).get(name) for name in METRICS},
        }
        for r in rows
    ]


def _range(row: RunRow) -> str:
    return f"{row.request['from']} to {row.request['to']}"
