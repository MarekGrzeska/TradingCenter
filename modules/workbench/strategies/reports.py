"""What a run came to, as numbers and nothing else: no field says whether the strategy is good (`strategies-reports`).
R first — it does not depend on the instrument — and money as nominal units × points (design D6)."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import numpy as np

from .costs import CostModel
from .engine import Result, Trade, simulate
from .evaluate import Evaluator
from .series import PERIOD_SECONDS, Series

# Calendar days, because a CFD account is marked every day and financing is charged on weekends too.
ANNUALISATION = "daily returns of nominal equity, scaled by sqrt(365)"


def build(
    result: Result,
    *,
    decision: Series,
    minute: Series,
    costs: CostModel,
    capital: float,
    range_from: int,
    range_to: int,
    random_entry: dict[str, Any] | None,
) -> dict[str, Any]:
    trades = result.trades
    equity = daily_equity(trades, minute, costs, capital, range_from, range_to)
    report: dict[str, Any] = {
        "trades": len(trades),
        "no_trades": not trades,
        "rejected_entries": result.rejected_entries,
        "decision_bars": result.decision_bars,
        "pessimistic_resolutions": sum(t.pessimistic for t in trades),
        **trade_metrics(trades, PERIOD_SECONDS[decision.resolution], range_to - range_from),
        **equity_metrics(equity, capital),
        "by_year": by_year(trades),
        "costs": {k: sum(t.costs[k] for t in trades) for k in ("spread", "slippage", "financing")},
        "benchmarks": {
            "buy_and_hold": buy_and_hold(minute, costs, capital, range_from, range_to),
            "random_entry": random_entry,
        },
        "annualisation": ANNUALISATION,
    }
    return finite(report)


def finite(value: Any) -> Any:
    """The report with every NaN or infinity as null: jsonb has neither, and an unmeasurable number is an empty one."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: finite(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [finite(v) for v in value]
    return value


def trade_metrics(trades: Sequence[Trade], bar_seconds: int, range_seconds: int) -> dict[str, Any]:
    """Every metric a list of trades alone answers. Empty — never zero — where there is nothing to measure."""
    if not trades:
        return {
            "win_rate": None, "expectancy_r": None, "total_r": None, "profit_factor": None,
            "max_drawdown_r": None, "longest_losing_streak": None, "average_bars_held": None,
            "exposure": None, "total_r_without_best_5": None,
        }
    r = np.array([t.result_r for t in trades])
    gains = sum(t.result_money for t in trades if t.result_money > 0)
    losses = -sum(t.result_money for t in trades if t.result_money < 0)
    curve = np.concatenate([[0.0], np.cumsum(r)])
    streak = longest = 0
    for value in r:
        streak = streak + 1 if value < 0 else 0
        longest = max(longest, streak)
    held = [(t.exit_time - t.entry_time) / bar_seconds for t in trades]
    return {
        "win_rate": float(np.mean(r > 0)),
        "expectancy_r": float(r.mean()),
        "total_r": float(r.sum()),
        "profit_factor": None if losses == 0 else float(gains / losses),
        "max_drawdown_r": float(np.max(np.maximum.accumulate(curve) - curve)),
        "longest_losing_streak": longest,
        "average_bars_held": float(np.mean(held)),
        "exposure": min(1.0, sum(t.exit_time - t.entry_time for t in trades) / max(range_seconds, 1)),
        "total_r_without_best_5": float(np.sort(r)[:-5].sum()) if len(r) > 5 else 0.0,
    }


def daily_equity(
    trades: Sequence[Trade], minute: Series, costs: CostModel, capital: float, range_from: int, range_to: int
) -> list[tuple[int, float]]:
    """Equity at each UTC midnight of the range and at its end: realised results, plus open positions marked at the last
    minute close before the mark — at the bid for a long, the ask for a short."""
    marks = list(range((range_from // 86400 + 1) * 86400, range_to, 86400)) + [range_to]
    closes = minute.columns["close"]
    out: list[tuple[int, float]] = [(range_from, capital)]
    for mark in marks:
        realised = sum(t.result_money for t in trades if t.exit_time <= mark)
        index = int(np.searchsorted(minute.available, mark, side="right")) - 1
        open_value = 0.0
        if index >= 0:
            for t in trades:
                if t.entry_time <= mark < t.exit_time:
                    side = 1 if t.side == "long" else -1
                    price = closes[index] + (costs.spread_at(int(minute.starts[index])) if side < 0 else 0.0)
                    open_value += side * (price - t.entry_price) * t.units
        out.append((mark, capital + realised + open_value))
    return out


def equity_metrics(equity: Sequence[tuple[int, float]], capital: float) -> dict[str, Any]:
    values = np.array([v for _, v in equity])
    peak = np.maximum.accumulate(values)
    drawdown = float(np.max((peak - values) / peak)) if len(values) else 0.0
    returns = values[1:] / values[:-1] - 1 if len(values) > 1 else np.array([])
    days = (equity[-1][0] - equity[0][0]) / 86400 if len(equity) > 1 else 0
    sharpe = sortino = calmar = None
    if len(returns) >= 2 and np.std(returns) > 0:
        sharpe = float(np.mean(returns) / np.std(returns) * math.sqrt(365))
    downside = math.sqrt(float(np.mean(np.minimum(returns, 0) ** 2))) if len(returns) else 0.0
    if len(returns) >= 2 and downside > 0:
        sortino = float(np.mean(returns) / downside * math.sqrt(365))
    annual = None
    if days > 0 and values[-1] > 0:
        annual = float((values[-1] / capital) ** (365 / days) - 1)
        if drawdown > 0:
            calmar = annual / drawdown
    return {
        "final_equity": float(values[-1]) if len(values) else capital,
        "return_pct": float(values[-1] / capital - 1) if len(values) else 0.0,
        "annual_return_pct": annual,
        "max_drawdown_pct": drawdown,
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar,
    }


def by_year(trades: Sequence[Trade]) -> dict[str, dict[str, float]]:
    years: dict[str, dict[str, float]] = defaultdict(lambda: {"trades": 0, "total_r": 0.0})
    for t in trades:
        year = str(datetime.fromtimestamp(t.exit_time, tz=UTC).year)
        years[year]["trades"] += 1
        years[year]["total_r"] += t.result_r
    return dict(sorted(years.items()))


def buy_and_hold(minute: Series, costs: CostModel, capital: float, range_from: int, range_to: int) -> dict[str, Any] | None:
    """The whole capital long from the range's first minute to its last, with the same costs."""
    inside = np.flatnonzero((minute.starts >= range_from) & (minute.available <= range_to))
    if inside.size == 0:
        return None
    first, last = int(inside[0]), int(inside[-1])
    entry = minute.columns["open"][first] + costs.spread_at(int(minute.starts[first])) + costs.slippage
    leave = minute.columns["close"][last] - costs.slippage
    units = capital / entry
    financing = costs.nights(int(minute.starts[first]), int(minute.available[last])) * costs.overnight_long * capital
    money = (leave - entry) * units - financing
    return {"return_pct": float(money / capital), "entry_price": float(entry), "exit_price": float(leave)}


def random_entry(
    result: Result,
    *,
    simulate_args: Mapping[str, Any],
    evaluator: Evaluator,
    decision: Series,
    range_from: int,
    range_to: int,
    seed: int,
    repetitions: int,
) -> dict[str, Any] | None:
    """As many entries as the strategy made, on decision bars drawn at random from the range, long or short in the
    strategy's own proportion, with its exits, sizing and costs — repeated, and reproducible from `seed`."""
    count = len(result.trades)
    candidates = np.flatnonzero((decision.starts >= range_from) & (decision.available <= range_to))
    if count == 0 or candidates.size == 0:
        return None
    long_share = sum(t.side == "long" for t in result.trades) / count
    rng = np.random.default_rng(seed)
    totals = []
    for _ in range(repetitions):
        bars = rng.choice(candidates, size=min(count, candidates.size), replace=False)
        sides = np.where(rng.random(bars.size) < long_share, 1, -1)
        forced = {int(b): int(s) for b, s in zip(bars, sides, strict=True)}
        drawn = simulate(**simulate_args, forced=forced, evaluator=evaluator)
        totals.append(sum(t.result_r for t in drawn.trades))
    values = np.array(totals)
    return {
        "repetitions": repetitions,
        "seed": seed,
        "median_total_r": float(np.median(values)),
        "p5_total_r": float(np.percentile(values, 5)),
        "p95_total_r": float(np.percentile(values, 95)),
    }
