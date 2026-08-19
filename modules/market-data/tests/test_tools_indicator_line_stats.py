"""The arithmetic behind `mode="latest"`, called directly.

Unit tests against three functions rather than through a tool: what they compute — a
line's last settled value, its slope, and how long since price last crossed it — is where
an off-by-one is invisible in a rendered reply.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from market_data.tools.indicators import _bars_since_cross, _last_non_none_index, _line_latest

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
