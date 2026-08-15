from __future__ import annotations

from market_mcp.reduce import aggregate_candles, truncate


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
