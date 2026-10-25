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
from .series import Series

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
        **trade_metrics(trades, decision.starts, range_to - range_from),
        **equity_metrics(equity, capital, capital + sum(t.result_money for t in trades)),
        "by_year": by_year(trades),
        "costs": {k: sum(t.costs[k] for t in trades) for k in ("spread", "slippage", "financing")},
        "benchmarks": {
            "buy_and_hold": buy_and_hold(minute, costs, capital, range_from, range_to),
            "random_entry": random_entry,
        },
        "annualisation": ANNUALISATION,
        # The series the ratios above were computed from, so a screen draws the curve the drawdown was measured on.
        "equity": [[mark, value] for mark, value in equity],
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


def trade_metrics(trades: Sequence[Trade], decision_starts: np.ndarray, range_seconds: int) -> dict[str, Any]:
    """Every metric a list of trades alone answers. Empty — never zero — where there is nothing to measure."""
    if not trades:
        return {
            "win_rate": None, "expectancy_r": None, "expectancy_pct": None, "total_r": None, "profit_factor": None,
            "max_drawdown_r": None, "longest_losing_streak": None, "average_bars_held": None,
            "exposure": None, "total_r_without_best_5": None, "total_pct_without_best_5": None, "worst_mae_pct": None,
        }
    r = np.array([t.result_r for t in trades])
    money = np.array([t.result_money for t in trades])
    pct = np.array([t.result_pct for t in trades])
    # Without a stop every R is NaN, and every metric in R is empty rather than a sum of nothing.
    in_r = bool(np.all(np.isfinite(r)))
    gains = float(money[money > 0].sum())
    losses = -float(money[money < 0].sum())
    curve = np.concatenate([[0.0], np.cumsum(r)])
    streak = longest = 0
    for value in money:
        streak = streak + 1 if value < 0 else 0
        longest = max(longest, streak)
    best_first = np.argsort(-money, kind="stable")
    # Decision bars that started while the position was open — a weekend is no bars, not sixty.
    entries = np.searchsorted(decision_starts, [t.entry_time for t in trades])
    exits = np.searchsorted(decision_starts, [t.exit_time for t in trades])
    return {
        "win_rate": float(np.mean(money > 0)),
        "expectancy_r": float(r.mean()) if in_r else None,
        "expectancy_pct": float(pct.mean()),
        "total_r": float(r.sum()) if in_r else None,
        "profit_factor": None if losses == 0 else float(gains / losses),
        "max_drawdown_r": float(np.max(np.maximum.accumulate(curve) - curve)) if in_r else None,
        "longest_losing_streak": longest,
        "average_bars_held": float(np.mean(exits - entries)),
        "exposure": min(1.0, sum(t.exit_time - t.entry_time for t in trades) / max(range_seconds, 1)),
        "total_r_without_best_5": (float(np.sort(r)[:-5].sum()) if len(r) > 5 else 0.0) if in_r else None,
        "total_pct_without_best_5": float(pct[best_first[5:]].sum()),
        "worst_mae_pct": float(min(t.mae_pct for t in trades)),
    }


def daily_equity(
    trades: Sequence[Trade], minute: Series, costs: CostModel, capital: float, range_from: int, range_to: int
) -> list[tuple[int, float]]:
    """Equity at each UTC midnight inside the range — whole days only, so every return is a day's. Realised results,
    plus the open position marked at the last minute close before the mark (bid for a long, ask for a short), less the
    financing it has accrued, as the realised result of the same trade will be."""
    marks = np.arange((range_from // 86400 + 1) * 86400, range_to + 1, 86400)
    by_exit = sorted(trades, key=lambda t: t.exit_time)
    exit_times = np.array([t.exit_time for t in by_exit], dtype=np.int64)
    realised = np.concatenate([[0.0], np.cumsum([t.result_money for t in by_exit])])
    by_entry = sorted(trades, key=lambda t: t.entry_time)
    entry_times = np.array([t.entry_time for t in by_entry], dtype=np.int64)
    closes = minute.columns["close"]
    out: list[tuple[int, float]] = []
    for mark in marks.tolist():
        value = capital + realised[int(np.searchsorted(exit_times, mark, side="right"))]
        # One position at a time: the last one entered by the mark is the only one that can still be open.
        last = int(np.searchsorted(entry_times, mark, side="right")) - 1
        index = int(np.searchsorted(minute.available, mark, side="right")) - 1
        if last >= 0 and index >= 0 and by_entry[last].exit_time > mark:
            t = by_entry[last]
            side = 1 if t.side == "long" else -1
            price = closes[index] + (costs.spread_at(int(minute.starts[index])) if side < 0 else 0.0)
            value += side * (price - t.entry_price) * t.units
            value -= costs.financing(side, t.units, t.entry_price, t.entry_time, mark)
        out.append((mark, value))
    return out


def equity_metrics(equity: Sequence[tuple[int, float]], capital: float, final: float) -> dict[str, Any]:
    """`final` is the equity at the range's end, which a midnight mark may not reach."""
    values = np.array([v for _, v in equity])
    result: dict[str, Any] = {
        "final_equity": final, "return_pct": final / capital - 1, "annual_return_pct": None,
        "max_drawdown_pct": None, "sharpe": None, "sortino": None, "calmar": None,
    }
    if len(values) < 2:
        return result
    peak = np.maximum.accumulate(np.concatenate([[capital], values]))
    curve = np.concatenate([[capital], values])
    if np.min(curve) <= 0:
        # A return off an empty or negative account is not a return; the curve is shown, its ratios are not.
        result["max_drawdown_pct"] = 1.0
        return result
    drawdown = float(np.max((peak - curve) / peak))
    returns = values[1:] / values[:-1] - 1
    days = (equity[-1][0] - equity[0][0]) / 86400
    result["max_drawdown_pct"] = drawdown
    if np.std(returns) > 0:
        result["sharpe"] = float(np.mean(returns) / np.std(returns) * math.sqrt(365))
    downside = math.sqrt(float(np.mean(np.minimum(returns, 0) ** 2)))
    if downside > 0:
        result["sortino"] = float(np.mean(returns) / downside * math.sqrt(365))
    if days > 0:
        annual = float((values[-1] / values[0]) ** (365 / days) - 1)
        result["annual_return_pct"] = annual
        if drawdown > 0:
            result["calmar"] = annual / drawdown
    return result


def by_year(trades: Sequence[Trade]) -> dict[str, dict[str, float]]:
    years: dict[str, dict[str, float]] = defaultdict(lambda: {"trades": 0, "total_r": 0.0, "total_pct": 0.0})
    for t in trades:
        year = str(datetime.fromtimestamp(t.exit_time, tz=UTC).year)
        years[year]["trades"] += 1
        years[year]["total_r"] += t.result_r
        years[year]["total_pct"] += t.result_pct
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
    financing = costs.financing(1, units, entry, int(minute.starts[first]), int(minute.available[last]))
    money = (leave - entry) * units - financing
    return {"return_pct": float(money / capital), "entry_price": float(entry), "exit_price": float(leave)}


def random_entry(result: Result, *, simulate_args: Mapping[str, Any], evaluator: Evaluator, seed: int, repetitions: int):
    """As many entries as the strategy made, on decision bars drawn at random from the range, long or short in the
    strategy's own proportion, as market orders with its exits, sizing and costs — repeated, reproducible from `seed`."""
    checked, series = simulate_args["checked"], simulate_args["series"]
    range_from, range_to = simulate_args["range_from"], simulate_args["range_to"]
    decision = series[(checked.document.symbol, checked.document.timeframe)]
    count = len(result.trades)
    candidates = np.flatnonzero((decision.starts >= range_from) & (decision.available <= range_to))
    if count == 0 or candidates.size == 0:
        return None
    long_share = sum(t.side == "long" for t in result.trades) / count
    rng = np.random.default_rng(seed)
    totals, returns, made = [], [], []
    for _ in range(repetitions):
        bars = np.sort(rng.choice(candidates, size=min(count, candidates.size), replace=False))
        sides = np.where(rng.random(bars.size) < long_share, 1, -1)
        drawn = simulate(**simulate_args, forced=list(zip(bars.tolist(), sides.tolist(), strict=True)), evaluator=evaluator)
        totals.append(sum(t.result_r for t in drawn.trades))
        returns.append(sum(t.result_money for t in drawn.trades) / simulate_args["capital"])
        made.append(len(drawn.trades))
    # NaN for a strategy without a stop, which `finite` turns into empty.
    values, gained = np.array(totals), np.array(returns)
    return {
        "repetitions": repetitions,
        "seed": seed,
        "entry": "market",
        "average_trades": float(np.mean(made)),
        "median_total_r": float(np.median(values)),
        "p5_total_r": float(np.percentile(values, 5)),
        "p95_total_r": float(np.percentile(values, 95)),
        "median_return_pct": float(np.median(gained)),
        "p5_return_pct": float(np.percentile(gained, 5)),
        "p95_return_pct": float(np.percentile(gained, 95)),
    }
