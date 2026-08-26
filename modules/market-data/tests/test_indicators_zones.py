"""`market-data-indicators`, "Strefy mają granice, kierunek i moment domknięcia" — small, hand-computed
series, tested the way `test_indicators_structure.py` tests W1."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pytest
from computers import fn_of

from market_data.indicators.catalogue import (
    IndicatorSpec,
    MinuteZones,
    Series,
    Zone,
    Zones,
    get,
)

LONDON = ZoneInfo("Europe/London")


def _series(high: list[float], low: list[float]) -> Series:
    high_arr = np.array(high, dtype=np.float64)
    low_arr = np.array(low, dtype=np.float64)
    close = (high_arr + low_arr) / 2
    return Series(open=close.copy(), high=high_arr, low=low_arr, close=close)


def _no_session_gaps(n: int) -> np.ndarray:
    return np.zeros(n, dtype=bool)


def _own_series_zones(
    entry: IndicatorSpec, series: Series, params: dict[str, float], session_close_before: np.ndarray
) -> list[Zone]:
    return fn_of(entry, Zones)(series, params, session_close_before)


def _minute_zones(
    entry: IndicatorSpec, series: Series, times: list[datetime], params: dict[str, float]
) -> list[Zone]:
    return fn_of(entry, MinuteZones)(series, times, params)


class TestRangeGap:
    def test_bullish_gap_between_bar_before_and_bar_after(self):
        # bar0's high (10) sits below bar2's low (20) — a void bar1 (the
        # impulse candle) never trades back into.
        entry = get("range_gap")
        zones = _own_series_zones(
            entry,
            _series(high=[10.0, 15.0, 21.0], low=[9.0, 14.0, 20.0]),
            {"skip_session_gaps": 0},
            _no_session_gaps(3),
        )

        [zone] = zones
        assert zone.start_bar == 0
        assert zone.direction == "bullish"
        assert zone.top == pytest.approx(20.0)
        assert zone.bottom == pytest.approx(10.0)

    def test_bearish_gap_mirrors_bullish(self):
        entry = get("range_gap")
        zones = _own_series_zones(
            entry,
            _series(high=[20.0, 15.0, 9.0], low=[19.0, 14.0, 8.0]),
            {"skip_session_gaps": 0},
            _no_session_gaps(3),
        )

        [zone] = zones
        assert zone.direction == "bearish"
        assert zone.top == pytest.approx(19.0)
        assert zone.bottom == pytest.approx(9.0)

    def test_no_gap_when_ranges_overlap(self):
        entry = get("range_gap")
        zones = _own_series_zones(
            entry,
            _series(high=[10.0, 15.0, 10.5], low=[9.0, 14.0, 9.5]),
            {"skip_session_gaps": 0},
            _no_session_gaps(3),
        )
        assert zones == []

    def test_touched_without_being_filled_stays_open(self):
        # Bar 3 dips into the gap (low=15 <= top=20) without reaching bar 0's
        # high (10) — touched, not filled.
        entry = get("range_gap")
        zones = _own_series_zones(
            entry,
            _series(high=[10.0, 15.0, 21.0, 16.0], low=[9.0, 14.0, 20.0, 15.0]),
            {"skip_session_gaps": 0},
            _no_session_gaps(4),
        )

        [zone] = zones
        assert zone.touched_at_bar == 3
        assert zone.filled_at_bar is None
        assert zone.end_bar is None

    def test_a_gap_never_touches_itself_at_formation(self):
        """The bar that forms the gap's own far edge must not count as the bar that later touches it —
        regression for the off-by-one where the scan started at the gap's own third bar."""
        entry = get("range_gap")
        zones = _own_series_zones(
            entry,
            _series(high=[10.0, 15.0, 21.0], low=[9.0, 14.0, 20.0]),
            {"skip_session_gaps": 0},
            _no_session_gaps(3),
        )

        [zone] = zones
        assert zone.touched_at_bar is None
        assert zone.filled_at_bar is None
        assert zone.end_bar is None

    def test_filled_closes_the_zone(self):
        entry = get("range_gap")
        # Bar 3 touches (low=15 <= top=20); bar 4 fills (low=9 <= bottom=10).
        zones = _own_series_zones(
            entry,
            _series(high=[10.0, 15.0, 21.0, 16.0, 9.5], low=[9.0, 14.0, 20.0, 15.0, 9.0]),
            {"skip_session_gaps": 0},
            _no_session_gaps(5),
        )

        zone = next(z for z in zones if z.start_bar == 0)
        assert zone.touched_at_bar == 3
        assert zone.filled_at_bar == 4
        assert zone.end_bar == 4

    def test_skip_session_gaps_suppresses_a_gap_spanning_a_market_close(self):
        entry = get("range_gap")
        series = _series(high=[10.0, 15.0, 21.0], low=[9.0, 14.0, 20.0])
        session_close_before = np.array([False, True, False], dtype=bool)

        skipped = _own_series_zones(entry, series, {"skip_session_gaps": 1}, session_close_before)
        assert skipped == []

        kept = _own_series_zones(entry, series, {"skip_session_gaps": 0}, session_close_before)
        assert len(kept) == 1


class TestBodyGap:
    def test_uses_bodies_not_wicks(self):
        # Wicks overlap (bar0 reaches up to 20, bar2's low is 19 — no wick
        # gap), but bodies (open/close) gap cleanly from 5 to 21.
        series = Series(
            open=np.array([5.0, 10.0, 21.0]),
            high=np.array([20.0, 18.0, 23.0]),
            low=np.array([4.0, 8.0, 19.0]),
            close=np.array([5.0, 10.5, 21.5]),
        )
        range_gap = get("range_gap")
        assert _own_series_zones(range_gap, series, {"skip_session_gaps": 0}, _no_session_gaps(3)) == []

        body_gap = get("body_gap")
        [zone] = _own_series_zones(body_gap, series, {"skip_session_gaps": 0}, _no_session_gaps(3))
        assert zone.direction == "bullish"
        assert zone.bottom == pytest.approx(5.0)  # bar0's body top (max(open,close))
        assert zone.top == pytest.approx(21.0)  # bar2's body bottom (min(open,close))


class TestSessionRange:
    def _minute(self, local_hour: float, day: int, month: int = 3, year: int = 2026) -> datetime:
        hour = int(local_hour)
        minute = round((local_hour - hour) * 60)
        local = datetime(year, month, day, hour, minute, tzinfo=LONDON)
        return local.astimezone(UTC)

    def test_recognises_the_same_local_hours_across_a_dst_change(self):
        """The UK springs forward at 01:00 UTC on 2026-03-29, so local 08:00 is 08:00 UTC on the 28th and 07:00 on
        the 30th: a window keyed on a fixed UTC offset would get one of the two wrong."""
        times = [
            self._minute(7.5, day=28),  # before the session, pre-DST
            self._minute(8.0, day=28),  # inside, pre-DST (GMT, UTC+0)
            self._minute(7.5, day=30),  # before the session, post-DST
            self._minute(8.0, day=30),  # inside, post-DST (BST, UTC+1)
        ]
        series = _series(high=[1.0, 2.0, 3.0, 4.0], low=[1.0, 2.0, 3.0, 4.0])
        entry = get("session_range_london")
        params = {"from_hour": 8.0, "to_hour": 16.5}

        zones = _minute_zones(entry, series, times, params)

        assert len(zones) == 2
        assert zones[0].start_bar == 1
        assert zones[0].top == pytest.approx(2.0)
        assert zones[1].start_bar == 3
        assert zones[1].top == pytest.approx(4.0)
        # Two calendar days apart is 48 hours; these are 47, because the same local clock time landed
        # an hour earlier in UTC when the offset moved under it (GMT to BST).
        assert times[3] - times[1] == timedelta(hours=47)

    def test_window_still_forming_stays_open(self):
        times = [self._minute(8.0, day=28), self._minute(9.0, day=28)]
        series = _series(high=[2.0, 5.0], low=[2.0, 1.0])
        entry = get("session_range_london")
        zones = _minute_zones(entry, series, times, {"from_hour": 8.0, "to_hour": 16.5})

        [zone] = zones
        assert zone.end_bar is None
        assert zone.top == pytest.approx(5.0)
        assert zone.bottom == pytest.approx(1.0)

    def test_two_consecutive_days_never_merge_into_one_zone(self):
        """A window closing right at midnight — in-window on the last bar of one day and the first of the next —
        must still produce two zones, not one that silently spans the boundary."""
        entry = get("session_range_london")
        # 23:00 local both days is inside a 22:00-23:30 window.
        times = [self._minute(23.0, day=28), self._minute(23.0, day=29)]
        series = _series(high=[10.0, 20.0], low=[10.0, 20.0])
        zones = _minute_zones(entry, series, times, {"from_hour": 22.0, "to_hour": 23.5})

        assert len(zones) == 2
        assert [z.start_bar for z in zones] == [0, 1]


class TestOpeningRange:
    def test_keeps_only_the_first_window_minutes_of_each_utc_day(self):
        base = datetime(2026, 6, 1, tzinfo=UTC)
        times = [
            base,  # 00:00 — inside a 30-minute window
            base + timedelta(minutes=29),  # inside
            base + timedelta(minutes=45),  # outside — after the window
            base + timedelta(days=1),  # next day, inside its own window
        ]
        series = _series(high=[10.0, 12.0, 99.0, 5.0], low=[9.0, 8.0, 1.0, 4.0])
        entry = get("opening_range")
        zones = _minute_zones(entry, series, times, {"window_minutes": 30, "n": 5})

        assert len(zones) == 2
        assert zones[0].start_bar == 0
        assert zones[0].end_bar == 1
        assert zones[0].top == pytest.approx(12.0)
        assert zones[0].bottom == pytest.approx(8.0)
        assert zones[1].start_bar == 3
        assert zones[1].end_bar is None  # the read range ends inside it

    def test_capped_to_the_most_recent_n(self):
        base = datetime(2026, 6, 1, tzinfo=UTC)
        times = [base + timedelta(days=d) for d in range(5)]
        series = _series(high=[1.0, 2.0, 3.0, 4.0, 5.0], low=[1.0, 2.0, 3.0, 4.0, 5.0])
        entry = get("opening_range")
        zones = _minute_zones(entry, series, times, {"window_minutes": 30, "n": 2})

        assert len(zones) == 2
        assert [z.start_bar for z in zones] == [3, 4]
