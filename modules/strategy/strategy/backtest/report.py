"""One run's result, and the rule that keeps two comparable: a report names its range, cost model, parameter version
and revision, or it is a number somebody produced. The revision is `compare`'s one exception, being its question."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .costs import CostModel
from .metrics import FeatureSplit, Metrics


class NotComparable(ValueError):
    """Two runs that cannot honestly be put side by side."""


@dataclass(frozen=True)
class Report:
    strategy_id: str
    symbol: str
    resolution: str
    range_from: datetime
    range_to: datetime
    params: dict[str, float]
    costs: CostModel
    metrics: Metrics
    # The rule this run computed, when it was one that was written down. `None` means the
    # strategy is code in the image, whose rule is in the repository under that id.
    strategy_revision: int | None = None
    strategy_revision_id: int | None = None
    attribution: list[FeatureSplit] = field(default_factory=list)
    # Every bar the range held, and what the platform said on each. A run that refused almost everything
    # for want of data looks identical in its metrics to one that found no setups.
    bars: int = 0
    refusals: dict[str, int] = field(default_factory=dict)
    # Filled in by the caller, which is the only place a clock is allowed: nothing in the
    # replay may read one, or the run would stop being reproducible.
    ran_at: datetime | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "resolution": self.resolution,
            "range_from": self.range_from.isoformat(),
            "range_to": self.range_to.isoformat(),
            "params": dict(self.params),
            "strategy_revision": self.strategy_revision,
            "costs": self.costs.as_dict(),
            "metrics": self.metrics.as_dict(),
            "attribution": [split.as_dict() for split in self.attribution],
            "bars": self.bars,
            "refusals": dict(self.refusals),
            "ran_at": self.ran_at.isoformat() if self.ran_at else None,
        }

    @property
    def comparable_on(self) -> tuple:
        """What two runs must share before their numbers may be read together. The revision is not here:
        two revisions on the same data and costs are the comparison this command is for."""
        return (self.symbol, self.resolution, self.range_from, self.range_to, self.costs)

    @property
    def named(self) -> str:
        """The strategy as a reader should see it — with its revision when it has one."""
        if self.strategy_revision is None:
            return self.strategy_id
        return f"{self.strategy_id}@{self.strategy_revision}"

    def summary(self) -> str:
        """The run in a few lines, for a terminal. Costs first, deliberately: a reader who
        stops after one line should still know what was assumed."""
        metrics = self.metrics
        factor = "—" if metrics.profit_factor is None else f"{metrics.profit_factor:.2f}"
        lines = [
            f"{self.named} · {self.symbol} {self.resolution}",
            f"  range      {self.range_from:%Y-%m-%d} → {self.range_to:%Y-%m-%d} ({self.bars} bars)",
            f"  costs      {self.costs.describe()}",
            f"  params     {self.params}",
            (
                f"  trades     {metrics.trades} ({metrics.wins} won, {metrics.win_rate:.0%}),"
                f" {metrics.unresolved} unresolved"
            ),
            (
                f"  expectancy {metrics.expectancy_r:+.3f}R   total {metrics.total_r:+.1f}R"
                f"   profit factor {factor}"
            ),
            (
                f"  worst run  {metrics.max_drawdown_r:.1f}R,"
                f" {metrics.longest_losing_streak} losses in a row"
            ),
            f"  refused    {self.refusals}",
        ]
        return "\n".join(lines)


def compare(reports: list[Report]) -> list[Report]:
    """The same reports, once it is established they may be compared at all. Returns them rather than a
    table on purpose: what to render is the caller's business, and the refusal is what this is for."""
    if len(reports) < 2:
        raise NotComparable("comparing needs at least two runs")
    first = reports[0].comparable_on
    for report in reports[1:]:
        if report.comparable_on != first:
            raise NotComparable(
                "these runs are not comparable: "
                f"{reports[0].strategy_id} ran on {_describe(reports[0])} and "
                f"{report.strategy_id} on {_describe(report)}. Two runs on different data "
                "or different costs are two different questions."
            )
    return reports


def _describe(report: Report) -> str:
    return (
        f"{report.symbol} {report.resolution} "
        f"{report.range_from:%Y-%m-%d}→{report.range_to:%Y-%m-%d} with {report.costs.describe()}"
    )
