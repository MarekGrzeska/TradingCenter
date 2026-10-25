"""The engine at its lowest layer, one scenario of `strategies-backtest` each, on minutes written by hand."""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from strategies.costs import CostModel
from strategies.document import servable, validate
from strategies.engine import simulate
from strategies.evaluate import Evaluator
from strategies.series import Series

from .builders import catalogue
from .market import FREE, HOUR, MONDAY, bars, flat, hours, minutes, run, strategy, walk

SPREAD = CostModel(spread=1.5, slippage=0.0, overnight_long=0.0, overnight_short=0.0, rollover_hour=22)


def test_a_signal_on_the_close_fills_on_the_open_of_the_next_minute_with_the_spread() -> None:
    result = run(strategy(), minutes(flat(9 * HOUR, 12 * HOUR, 100.0)), costs=SPREAD)

    [trade] = result.trades
    assert trade.entry_time == MONDAY + 10 * HOUR
    assert trade.entry_price == 101.5


def test_a_short_stop_is_touched_by_the_ask_though_the_bid_never_reaches_it() -> None:
    rows = flat(9 * HOUR, 12 * HOUR, 100.0)
    rows[10 * HOUR + 300] = (100.0, 109.0, 100.0, 100.0)  # bid high 109; ask high 110.5 against a stop at 110
    document = strategy(entries=[{"side": "short", "when": "hour == 9"}], exits={"stop": "entry_price + 10"})

    [trade] = run(document, minutes(rows), costs=SPREAD).trades

    assert trade.entry_price == 100.0 and trade.exit_reason == "stop" and trade.exit_time == MONDAY + 10 * HOUR + 300


def test_a_stop_entry_jumped_by_a_gap_fills_at_the_open_beyond_it() -> None:
    rows = flat(9 * HOUR, 10 * HOUR, 18_000.0) | flat(10 * HOUR + 60, 12 * HOUR, 18_040.0)
    document = strategy(
        entries=[{"side": "long", "when": "hour == 9", "order": {"type": "stop", "price": "18000.5"}}],
        exits={"stop": "entry_price - 100"},
    )

    [trade] = run(document, minutes(rows), costs=SPREAD).trades

    assert trade.entry_price == 18_041.5


def test_a_signal_while_a_position_is_open_is_not_a_second_one() -> None:
    document = strategy(entries=[{"side": "long", "when": "hour >= 9"}, {"side": "short", "when": "hour >= 9"}])

    trades = run(document, minutes(flat(9 * HOUR, 14 * HOUR, 100.0))).trades

    assert len(trades) == 1 and trades[0].side == "long" and trades[0].exit_reason == "end_of_range"


def test_a_trailing_stop_only_ever_tightens() -> None:
    rows = flat(9 * HOUR, 10 * HOUR + 60, 100.0) | flat(10 * HOUR + 60, 11 * HOUR, 130.0)
    rows |= flat(11 * HOUR, 12 * HOUR, 128.0)
    rows[12 * HOUR] = (128.0, 128.0, 100.0, 100.0)
    document = strategy(exits={"stop": "entry_price - 10", "trail": {"after_r": 1, "distance": "5"}})

    [trade] = run(document, minutes(rows)).trades

    # In at 100; trailed to 125 on the 11:00 close (130 − 5); the 12:00 close (128) would put it at 123 — a loosening,
    # refused — so the drop at 12:00 leaves at 125.
    assert trade.exit_reason == "trail" and trade.exit_price == 125.0


def test_after_the_daily_stop_nothing_is_entered_until_midnight_utc() -> None:
    rows = flat(9 * HOUR, 26 * HOUR, 100.0)
    rows[10 * HOUR + 60] = (100.0, 100.0, 40.0, 40.0)  # the first trade is stopped at −1 R
    rows |= flat(10 * HOUR + 120, 26 * HOUR, 40.0)
    document = strategy(
        entries=[{"side": "long", "when": "hour >= 9 or hour < 2"}],
        exits={"stop": "entry_price - 50", "max_bars": 1},
        limits={"daily_stop_r": -1},
    )

    trades = run(document, minutes(rows)).trades

    assert trades[0].exit_reason == "stop"
    assert all(t.entry_time >= MONDAY + 24 * HOUR for t in trades[1:]) and len(trades) > 1


def test_a_minute_spanning_both_stop_and_target_closes_on_the_stop_and_says_it_assumed() -> None:
    rows = flat(9 * HOUR, 12 * HOUR, 100.0)
    rows[10 * HOUR + 120] = (100.0, 130.0, 40.0, 100.0)
    document = strategy(exits={"stop": "entry_price - 50", "target": "entry_price + 20"})

    [trade] = run(document, minutes(rows)).trades

    assert trade.exit_reason == "stop" and trade.exit_price == 50.0 and trade.pessimistic


def test_risk_fraction_sizes_from_the_distance_to_the_stop() -> None:
    document = strategy(exits={"stop": "entry_price - 40"}, sizing={"mode": "risk_fraction", "value": 0.005})

    [trade] = run(document, minutes(flat(9 * HOUR, 12 * HOUR, 100.0)), capital=10_000.0).trades

    assert trade.units == pytest.approx(1.25)


def test_a_stop_on_the_wrong_side_of_the_fill_is_counted_never_traded() -> None:
    result = run(strategy(exits={"stop": "entry_price + 5"}), minutes(flat(9 * HOUR, 12 * HOUR, 100.0)))

    assert result.trades == [] and result.rejected_entries == 1


def test_an_unfilled_order_expires_after_its_bars() -> None:
    document = strategy(entries=[{
        "side": "long", "when": "hour == 9", "order": {"type": "stop", "price": "200", "expires_bars": 2},
    }])

    assert run(document, minutes(flat(9 * HOUR, 14 * HOUR, 100.0) | flat(14 * HOUR, 15 * HOUR, 250.0))).trades == []


def test_a_cost_model_has_no_defaults() -> None:
    with pytest.raises(ValidationError):
        CostModel()  # type: ignore[call-arg]


def test_a_long_held_from_friday_evening_to_monday_morning_pays_three_nights() -> None:
    friday_20, monday_10 = MONDAY + 4 * 86400 + 20 * HOUR, MONDAY + 7 * 86400 + 10 * HOUR

    assert SPREAD.nights(friday_20, monday_10) == 3


def test_financing_is_booked_on_the_trade() -> None:
    costs = CostModel(spread=0.0, slippage=0.0, overnight_long=0.001, overnight_short=0.0, rollover_hour=22)
    document = strategy(exits={"stop": "entry_price - 50"})

    [trade] = run(document, minutes(flat(9 * HOUR, 26 * HOUR, 100.0)), costs=costs).trades

    assert trade.costs["financing"] == pytest.approx(0.1)  # one night × 0.1% × 1 unit × 100


def test_a_longer_range_leaves_the_trades_of_the_shorter_one_as_they_were() -> None:
    minute = minutes(walk(14))
    document = strategy(
        entries=[{"side": "long", "when": "crosses_above(close, average(close, 20))"}],
        exits={"stop": "entry_price - 30", "target": "entry_price + 45", "max_bars": 12},
    )
    first_week_end = MONDAY + 7 * 86400

    short = run(document, minute, range_to=first_week_end).trades
    long = run(document, minute).trades

    closed = [t for t in short if t.exit_reason != "end_of_range"]
    assert closed and closed == long[: len(closed)]


def test_the_whole_axis_at_once_equals_the_axis_cut_at_each_bar() -> None:
    """The future cannot leak backwards: every formula's value on bar i is the same whether the series ends at i or not."""
    minute = minutes(walk(10, seed=3))
    hour = hours(minute)
    document = strategy(
        let={"m": "average(close, 10)", "h": "highest(high, 5)[1]"},
        entries=[{"side": "long", "when": "crosses_above(close, m) and close @ MINUTE > h and bars_since(close < m) < 4"}],
    )
    checked, problems = validate(document, catalogue(), servable({("US100", "MINUTE")}))
    assert checked is not None, problems
    node = checked.formulas["entries[0].when"]
    whole = Evaluator(checked, {}, catalogue(), {("US100", "HOUR"): hour, ("US100", "MINUTE"): minute}, {}).vector(node)

    for i in range(30, len(hour), 7):
        cut_hour = _cut(hour, i + 1)
        cut_minute = _cut(minute, int(np.searchsorted(minute.starts, hour.available[i], side="left")))
        cut = Evaluator(checked, {}, catalogue(), {("US100", "HOUR"): cut_hour, ("US100", "MINUTE"): cut_minute}, {})
        assert cut.vector(node)[i] == whole[i], i


def _cut(series: Series, size: int) -> Series:
    return Series(
        series.resolution, series.starts[:size], series.available[:size],
        {k: v[:size] for k, v in series.columns.items()},
    )


def test_free_costs_are_a_choice_written_down() -> None:
    assert FREE.spread == 0.0 and FREE.slippage == 0.0


def test_a_chain_of_at_reads_the_other_instrument_at_the_other_resolution_and_nothing_between() -> None:
    from strategies.requirements import needs

    minute = minutes(flat(9 * HOUR, 12 * HOUR, 100.0))
    day = Series("DAY", np.array([MONDAY - 86400], dtype=np.int64), np.array([MONDAY], dtype=np.int64),
                 {k: np.array([50.0]) for k in ("open", "high", "low", "close", "volume")})
    document = strategy(entries=[{"side": "long", "when": "hour == 9 and close @ US500 @ DAY > 10"}])
    checked, problems = validate(document, catalogue(), servable({("US100", "MINUTE"), ("US500", "DAY")}))
    assert checked is not None, problems

    assert needs(checked, {}, catalogue()).contexts == {("US100", "HOUR"), ("US100", "MINUTE"), ("US500", "DAY")}
    series = {("US100", "MINUTE"): minute, ("US100", "HOUR"): hours(minute), ("US500", "DAY"): day}
    from strategies.engine import simulate

    result = simulate(checked, {}, catalogue(), series, {}, FREE, 10_000.0, MONDAY, int(minute.available[-1]))
    assert len(result.trades) == 1


def test_an_order_whose_price_is_not_known_yet_is_counted_and_does_not_block_the_next_signal() -> None:
    document = strategy(entries=[
        {"side": "long", "when": "hour == 9", "order": {"type": "limit", "price": "close[30]"}},
        {"side": "long", "when": "hour == 11"},
    ], exits={"stop": "entry_price - 50", "max_bars": 1})

    result = run(document, minutes(flat(9 * HOUR, 14 * HOUR, 100.0)))

    assert result.rejected_entries == 1 and len(result.trades) == 1


def test_a_market_entry_stopped_later_in_its_own_minute_is_certain_not_assumed() -> None:
    rows = flat(9 * HOUR, 12 * HOUR, 100.0)
    rows[10 * HOUR] = (100.0, 100.0, 40.0, 40.0)

    [trade] = run(strategy(), minutes(rows)).trades

    assert trade.exit_reason == "stop" and not trade.pessimistic


# 2026-07-02, a Thursday: New York on summer time, 9:30 there is 13:30 UTC.
JULY_2 = MONDAY + 122 * 86400
SESSION = strategy(
    timeframe="MINUTE_5",
    entries=[{"side": "long", "when": "session_bar(NEW_YORK) == 1"}],
    exits={"when": "minutes_to_session_close(NEW_YORK) <= 5"},
)


def _offset(rows: dict[int, tuple[float, float, float, float]], by: int) -> dict[int, tuple[float, float, float, float]]:
    return {t + by: v for t, v in rows.items()}


def test_a_position_without_a_stop_leaves_five_minutes_before_new_york_closes() -> None:
    day = _offset(flat(13 * HOUR, 21 * HOUR, 100.0), JULY_2 - MONDAY)

    [trade] = run(SESSION, minutes(day), range_from=JULY_2).trades

    assert trade.entry_time == JULY_2 + 13 * HOUR + 35 * 60  # the open of the minute after the 13:30–13:35 bar
    assert trade.exit_time == JULY_2 + 19 * HOUR + 55 * 60 and trade.exit_reason == "when"  # 15:55 in New York
    assert np.isnan(trade.initial_stop) and np.isnan(trade.result_r)


@pytest.mark.parametrize(
    ("sizing", "margin_factor"),
    [({"mode": "margin_fraction", "value": 0.05}, 0.05), ({"mode": "notional_fraction", "value": 1}, None)],
)
def test_a_deposit_or_a_value_as_a_fraction_of_equity_sizes_the_position(sizing: dict, margin_factor) -> None:
    day = _offset(flat(13 * HOUR, 21 * HOUR, 20_000.0), JULY_2 - MONDAY)

    [trade] = run(SESSION | {"sizing": sizing}, minutes(day), range_from=JULY_2, margin_factor=margin_factor).trades

    assert trade.units == 0.5


def test_a_result_without_a_stop_is_in_percent_of_the_equity_at_entry_and_not_in_r() -> None:
    day = _offset(flat(13 * HOUR, 16 * HOUR, 100.0) | flat(16 * HOUR, 21 * HOUR, 250.0), JULY_2 - MONDAY)

    [trade] = run(SESSION, minutes(day), range_from=JULY_2).trades

    assert trade.result_money == 150.0 and trade.result_pct == 0.015 and np.isnan(trade.result_r)


def test_a_position_that_loses_the_whole_capital_is_closed_and_nothing_opens_after() -> None:
    rows = flat(9 * HOUR, 11 * HOUR, 20_000.0)
    rows[11 * HOUR] = (10_050.0, 10_050.0, 9_990.0, 9_990.0)
    rows |= flat(11 * HOUR + 60, 14 * HOUR, 9_990.0)
    document = strategy(entries=[{"side": "long", "when": "hour >= 9"}], exits={"max_bars": 100})

    trades = run(document, minutes(rows)).trades

    assert [(t.exit_price, t.exit_reason) for t in trades] == [(10_000.0, "out_of_capital")]


def _trade_path(trades) -> list[tuple]:
    return [(t.side, t.entry_time, t.entry_price, t.exit_time, t.exit_price) for t in trades]


def test_a_strategy_without_levels_trades_on_its_bars_as_it_would_on_minutes() -> None:
    """The same entries and exits, once with a stop too far to be touched, which settles them on minutes."""
    minute = minutes(walk(10))
    costs = CostModel(spread=1.5, slippage=0.2, overnight_long=0.0002, overnight_short=0.0001, rollover_hour=22)
    unreachable = {"stop": "entry_price - 100000", "when": SESSION["exits"]["when"]}

    on_bars = run(SESSION, minute, costs=costs).trades
    on_minutes = run(SESSION | {"exits": unreachable}, minute, costs=costs).trades

    assert len(on_bars) == 8 and _trade_path(on_bars) == _trade_path(on_minutes)


def test_a_strategy_without_levels_needs_no_minutes_under_its_bars() -> None:
    """No minute series at all: an engine that read one would fail on the missing key."""
    five = bars(minutes(walk(10)), "MINUTE_5")
    checked, problems = validate(SESSION, catalogue(), servable({("US100", "MINUTE")}))
    assert checked is not None, problems

    trades = simulate(
        checked, {}, catalogue(), {("US100", "MINUTE_5"): five}, {}, FREE, 10_000.0, MONDAY, int(five.available[-1])
    ).trades

    assert len(trades) == 8 and {t.exit_reason for t in trades} == {"when"}
