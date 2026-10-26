"""The signal at its lowest layer: the engine's state after its last decision, read as the action it calls for — and the
same decisions as the engine's own trades, bar by bar."""

from __future__ import annotations

import pytest

from strategies import signals
from strategies.signals import decide

from .market import HOUR, MONDAY, bars, flat, minutes, run, strategy, walk
from .test_engine import JULY_2, SESSION, _offset
from .test_tools import _app, _call

DAY = minutes(_offset(flat(13 * HOUR, 21 * HOUR, 100.0), JULY_2 - MONDAY))
M5 = bars(DAY, "MINUTE_5")


def _at(close: int):
    result = run(SESSION, DAY, range_from=JULY_2, range_to=close)
    assert result.in_flight is not None
    return decide(result.in_flight, M5)


def test_the_first_new_york_bar_closing_is_a_market_entry_signalled_on_it() -> None:
    action, order, position, _ = _at(JULY_2 + 13 * HOUR + 35 * 60)

    assert action == "enter" and position is None
    assert order is not None and order.side == "long" and order.kind == "market" and order.price is None
    assert order.signalled_at == "2026-07-02T13:35:00Z"


def test_after_the_fill_the_engine_holds_its_position() -> None:
    action, order, position, _ = _at(JULY_2 + 14 * HOUR)

    assert action == "hold" and order is None
    assert position is not None and position.entered_at == "2026-07-02T13:35:00Z" and position.stop is None


def test_five_minutes_before_new_york_closes_the_exit_is_due() -> None:
    action, _, position, reason = _at(JULY_2 + 19 * HOUR + 55 * 60)

    assert action == "exit" and reason == "when" and position is not None


def test_before_the_session_there_is_nothing_to_do() -> None:
    assert _at(JULY_2 + 13 * HOUR + 30 * 60)[0] == "none"


def test_every_trade_of_a_backtest_is_a_signal_on_the_same_bar() -> None:
    """`strategies-tools`, "Ta sama decyzja co backtest": the signal asked after each bar, against the trades of one run."""
    document = strategy(
        timeframe="MINUTE_5",
        entries=[{"side": "long", "when": "close > close[1] and close[1] > close[2]"},
                 {"side": "short", "when": "close < close[1] and close[1] < close[2]"}],
        exits={"when": "close < close[1] if position > 0 else close > close[1]", "max_bars": 6},
    )
    minute = minutes(walk(3, seed=11))
    m5 = bars(minute, "MINUTE_5")
    start = MONDAY + 2 * HOUR
    closes = [int(t) for t in m5.available if start + 3 * 300 <= t <= MONDAY + 10 * HOUR]
    trades = run(document, minute, range_from=start, range_to=closes[-1]).trades
    assert trades

    signals = {}
    for close in closes:
        result = run(document, minute, range_from=start, range_to=close)
        assert result.in_flight is not None
        signals[close] = decide(result.in_flight, m5)

    for trade in trades:
        if trade.exit_reason == "end_of_range":
            continue
        # Market orders on the decision series: entered at the open after the signal bar, which is that bar's close.
        assert signals[trade.entry_time][0] == "enter"
        assert signals[trade.entry_time][1].side == trade.side
        assert signals[trade.exit_time][0] == "exit"
    # And the other way: no entry signal the backtest did not take (the last bar's fills after the range).
    entered = {close for close, (action, *_) in signals.items() if action == "enter"} - {closes[-1]}
    assert entered == {trade.entry_time for trade in trades}


@pytest.mark.db
async def test_the_signal_reads_the_archive_and_writes_nothing(pool) -> None:
    """`strategies-tools`, "Sygnał nie jest próbą": asked as often as wanted, no run and no trial."""
    app = _app(pool)
    strategy_id = (await _call(app, "save_strategy", document=strategy()))["strategy_id"]
    # Monday 10:00 UTC: the 09:00–10:00 bar has just closed, and `hour == 9` enters on it.
    now = MONDAY + 10 * HOUR
    async with pool.acquire() as conn:
        found = [await signals.signal(conn, app.state.archive, strategy_id, 1, now) for _ in range(3)]
        runs_after = await conn.fetchval("SELECT count(*) FROM runs")

    assert {s.action for s in found} == {"enter"} and found[0].bar_closed_at == "2026-03-02T10:00:00Z"
    assert found[0].sizing == {"mode": "fixed_units", "value": 1.0} and found[0].costs_source == "none"
    assert runs_after == 0
