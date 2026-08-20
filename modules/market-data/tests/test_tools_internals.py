"""The arithmetic and the sentences behind the tool replies, called directly.

Three units that never needed a server between them and a test: the reduction that keeps
a reply under its ceiling, the sentences saying what the archive does not know, and the
`mode="latest"` line statistics — where an off-by-one is invisible once rendered.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from market_data.tools.indicators import _bars_since_cross, _last_non_none_index, _line_latest
from market_data.tools.reduce import aggregate_candles, truncate
from market_data.tools.uncertainty import (
    derived_sentence,
    empty_series_sentence,
    uncovered_sentence,
)

# --- reduce: keeping a reply under its ceiling ----------------------------------------


def _candle(time: str, open_: float, high: float, low: float, close: float) -> dict:
    return {"time": time, "open": open_, "high": high, "low": low, "close": close}


def test_series_within_target_is_unchanged() -> None:
    candles = [_candle(f"t{i}", 1, 2, 0, 1) for i in range(50)]
    result, agg = aggregate_candles(candles, target_count=200)
    assert result == candles
    assert agg is None


def test_series_above_target_is_bucketed() -> None:
    candles = [_candle(f"t{i}", i, i + 1, i - 1, i) for i in range(1000)]
    result, agg = aggregate_candles(candles, target_count=200)
    assert agg is not None
    assert agg.original_count == 1000
    assert len(result) <= 200


def test_bucket_merges_ohlc_correctly() -> None:
    candles = [
        _candle("t0", open_=10, high=12, low=9, close=11),
        _candle("t1", open_=11, high=15, low=10, close=14),
        _candle("t2", open_=14, high=14, low=8, close=9),
    ]
    result, agg = aggregate_candles(candles, target_count=1)
    assert agg is not None
    [bucket] = result
    assert bucket["time"] == "t0"
    assert bucket["open"] == 10
    assert bucket["high"] == 15
    assert bucket["low"] == 8
    assert bucket["close"] == 9


def test_bucket_skips_missing_values() -> None:
    candles = [
        _candle("t0", open_=None, high=None, low=None, close=None),
        _candle("t1", open_=5, high=6, low=4, close=5),
    ]
    result, _agg = aggregate_candles(candles, target_count=1)
    [bucket] = result
    assert bucket["open"] == 5
    assert bucket["high"] == 6
    assert bucket["low"] == 4
    assert bucket["close"] == 5


def test_truncate_under_limit_drops_nothing() -> None:
    items, dropped = truncate([1, 2, 3], limit=10)
    assert items == [1, 2, 3]
    assert dropped == 0


def test_truncate_over_limit_names_what_it_drops() -> None:
    items, dropped = truncate(list(range(30)), limit=10)
    assert items == list(range(10))
    assert dropped == 20


# --- uncertainty: saying what the archive does not know -------------------------------


def test_no_gaps_is_silent() -> None:
    assert uncovered_sentence([]) is None


def test_gap_names_the_stretch_and_warns_against_reading_it_as_quiet() -> None:
    gap = (datetime(2026, 8, 11, 9, 0, tzinfo=UTC), datetime(2026, 8, 11, 9, 30, tzinfo=UTC))
    sentence = uncovered_sentence([gap])
    assert sentence is not None
    assert "1 stretch" in sentence
    assert "not mean the market was quiet" in sentence


def test_not_derived_is_silent() -> None:
    assert derived_sentence(False, "HOUR") is None


def test_derived_names_the_resolution() -> None:
    sentence = derived_sentence(True, "HOUR")
    assert sentence is not None
    assert "HOUR" in sentence
    assert "not collected from the provider" in sentence


def test_untracked_pair_says_nobody_collects_it() -> None:
    sentence = empty_series_sentence("US100", tracked=False)
    assert "nobody is collecting it" in sentence
    assert "not because the market was quiet" in sentence


def test_tracked_pair_with_no_candle_points_at_coverage() -> None:
    sentence = empty_series_sentence("US100", tracked=True)
    assert "is tracked" in sentence
    assert "describe_coverage" in sentence


# --- indicator line statistics, the arithmetic behind `mode="latest"` -----------------

START = datetime(2026, 1, 1, tzinfo=UTC)


def _times(n: int) -> list[datetime]:
    return [START + timedelta(minutes=i) for i in range(n)]


def test_last_non_none_index_skips_trailing_nones() -> None:
    assert _last_non_none_index([1.0, 2.0, None, None]) == 1


def test_last_non_none_index_all_none() -> None:
    assert _last_non_none_index([None, None]) is None


def test_line_latest_with_no_settled_value() -> None:
    out = _line_latest("ema", "EMA", [None, None], _times(2), {})
    assert out.value is None
    assert out.slope_per_bar is None


def test_bars_since_cross_finds_the_flip() -> None:
    times = _times(5)
    # close is always 100; line crosses below close at index 3, was above through 0-2
    values = [101.0, 101.0, 101.0, 99.0, 99.0]
    closes = {t: 100.0 for t in times}
    assert _bars_since_cross(values, times, closes, last_idx=4) == 1


def test_bars_since_cross_with_no_flip_in_window() -> None:
    times = _times(5)
    values = [99.0] * 5
    closes = {t: 100.0 for t in times}
    assert _bars_since_cross(values, times, closes, last_idx=4) is None


def test_bars_since_cross_with_no_price_data() -> None:
    times = _times(3)
    values = [99.0, 99.0, 99.0]
    assert _bars_since_cross(values, times, {}, last_idx=2) is None
