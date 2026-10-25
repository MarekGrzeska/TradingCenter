"""The report at its lowest layer: metrics from trades given by hand, the benchmarks, and the absence of a verdict
(`strategies-reports`)."""

from __future__ import annotations

import numpy as np
import pytest

from strategies import reports, runs
from strategies.document import servable, validate
from strategies.engine import Trade, simulate
from strategies.evaluate import Evaluator

from .builders import catalogue
from .market import FREE, HOUR, MONDAY, flat, hours, minutes, strategy, walk


def trade(r: float, *, exit_time: int = MONDAY + 2 * HOUR, side: str = "long") -> Trade:
    return Trade(
        side=side, signal_bar=0, entry_time=MONDAY + HOUR, entry_price=100.0, exit_time=exit_time,
        exit_price=100.0 + 10 * r, units=1.0, initial_stop=90.0, result_r=r, result_money=10 * r,
        costs={"spread": 1.0, "slippage": 0.5, "financing": 0.0}, exit_reason="stop" if r < 0 else "target",
        pessimistic=False,
    )


HOURS = np.arange(MONDAY, MONDAY + 7 * 86400, HOUR)


def test_metrics_of_a_handful_of_trades() -> None:
    found = reports.trade_metrics([trade(2), trade(-1), trade(-1), trade(3)], HOURS, 10 * HOUR)

    assert found["win_rate"] == 0.5 and found["total_r"] == 3 and found["expectancy_r"] == 0.75
    assert found["profit_factor"] == pytest.approx(2.5) and found["max_drawdown_r"] == 2
    assert found["longest_losing_streak"] == 2 and found["exposure"] == pytest.approx(0.4)


def test_without_trades_every_trade_metric_is_empty_not_zero() -> None:
    assert set(reports.trade_metrics([], HOURS, HOUR).values()) == {None}


def test_without_a_loss_the_profit_factor_is_empty() -> None:
    assert reports.trade_metrics([trade(1), trade(2)], HOURS, HOUR)["profit_factor"] is None


def test_the_best_five_removed_shows_what_is_left() -> None:
    found = reports.trade_metrics([trade(r) for r in (5, 4, 3, 2, 1, -1, -2)], HOURS, HOUR)

    assert found["total_r_without_best_5"] == -3


def _report(document, minute, *, seed=1, repetitions=10):
    checked, problems = validate(document, catalogue(), servable({("US100", "MINUTE")}))
    assert checked is not None, problems
    series = {("US100", "MINUTE"): minute, ("US100", "HOUR"): hours(minute)}
    args = {
        "checked": checked, "params": {}, "catalogue": catalogue(), "series": series, "indicators": {},
        "costs": FREE, "capital": 10_000.0, "range_from": MONDAY, "range_to": int(minute.available[-1]),
    }
    evaluator = Evaluator(checked, {}, catalogue(), series, {})
    result = simulate(**args, evaluator=evaluator)
    benchmark = reports.random_entry(result, simulate_args=args, evaluator=evaluator, seed=seed, repetitions=repetitions)
    return reports.build(
        result, decision=series[("US100", "HOUR")], minute=minute, costs=FREE, capital=10_000.0,
        range_from=args["range_from"], range_to=args["range_to"], random_entry=benchmark,
    )


WALKING = strategy(
    entries=[{"side": "long", "when": "crosses_above(close, average(close, 20))"}],
    exits={"stop": "entry_price - 30", "target": "entry_price + 45", "max_bars": 12},
)


def test_the_random_entry_benchmark_repeats_exactly_with_the_same_seed() -> None:
    minute = minutes(walk(10, seed=5))

    first, second = _report(WALKING, minute)["benchmarks"]["random_entry"], _report(WALKING, minute)["benchmarks"]["random_entry"]

    assert first == second and first["repetitions"] == 10 and first["p5_total_r"] <= first["p95_total_r"]


def test_a_report_carries_numbers_and_no_verdict() -> None:
    report = _report(WALKING, minutes(walk(10, seed=5)))

    assert not {"verdict", "passed", "grade", "score", "ok", "good", "rating"} & set(report)
    assert report["trades"] > 0 and report["benchmarks"]["buy_and_hold"] is not None


def test_a_strategy_that_never_enters_says_so() -> None:
    report = _report(strategy(entries=[{"side": "long", "when": "hour == 99"}]), minutes(flat(0, 2 * 86400, 100.0)))

    assert report["no_trades"] and report["total_r"] is None and report["benchmarks"]["random_entry"] is None


def test_an_unmeasurable_number_is_stored_as_null() -> None:
    assert reports.finite({"a": float("nan"), "b": [float("inf"), 1.0]}) == {"a": None, "b": [None, 1.0]}


def test_bars_held_count_decision_bars_not_the_clock_over_a_weekend() -> None:
    friday_20, monday_10 = MONDAY + 4 * 86400 + 20 * HOUR, MONDAY + 7 * 86400 + 10 * HOUR
    weekday_hours = np.array([h for h in range(MONDAY, MONDAY + 8 * 86400, HOUR) if (h - MONDAY) // 86400 % 7 < 5])
    held = Trade("long", 0, friday_20, 100.0, monday_10, 100.0, 1.0, 90.0, 0.0, 0.0,
                 {"spread": 0, "slippage": 0, "financing": 0}, "when", False)

    assert reports.trade_metrics([held], weekday_hours, 86400)["average_bars_held"] == 14  # 20:00–24:00 Fri, 00–10 Mon


def test_equity_ratios_are_empty_once_the_account_is_not_positive() -> None:
    found = reports.equity_metrics([(0, 500.0), (86400, -200.0), (172800, -100.0)], 1000.0, -100.0)

    assert found["sharpe"] is None and found["max_drawdown_pct"] == 1.0


def test_random_entries_falling_inside_a_trade_are_taken_on_the_next_flat_bar() -> None:
    minute = minutes(walk(10, seed=5))
    random = _report(WALKING, minute, repetitions=5)
    strategy_trades = _report(WALKING, minute)["trades"]

    assert random["benchmarks"]["random_entry"]["average_trades"] >= 0.9 * strategy_trades


def test_the_curve_in_the_report_is_the_one_its_drawdown_was_measured_on() -> None:
    report = _report(WALKING, minutes(walk(10, seed=5)))
    values = np.array([10_000.0] + [value for _, value in report["equity"]])

    measured = float(np.max((np.maximum.accumulate(values) - values) / np.maximum.accumulate(values)))

    assert measured == pytest.approx(report["max_drawdown_pct"])
    assert [mark % 86400 for mark, _ in report["equity"]] == [0] * len(report["equity"])


def test_every_field_a_report_carries_has_its_place_in_the_contract() -> None:
    from strategies.contract import ReportOut

    report = _report(WALKING, minutes(walk(10, seed=5))) | runs.costs_marks({}, "operator")
    before_the_curve = {k: v for k, v in report.items() if k != "equity"}

    assert ReportOut.model_validate(report).model_dump(mode="json").keys() == report.keys()
    assert ReportOut.model_validate(before_the_curve).equity is None
