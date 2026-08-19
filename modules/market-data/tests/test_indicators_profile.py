"""`market-data-indicators` spec, "Profil czasowy liczy udział czasu, nie wolumenu" —
the W3 layer (`docs/wskazniki-plan-wdrozenia.html`), on the minute series
`time_profile` reads regardless of the resolution charted. Task 5.5's own words:
the point of control has to match a hand recount on a small sample.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from computers import fn_of

from market_data.indicators.catalogue import Series, TimeProfile, get


def _minute_series(mid: list[float]) -> tuple[Series, list[datetime]]:
    """Each bar's true range held to exactly 2.0 by construction (`high = mid +
    1`, `low = mid - 1`, `close = mid`, and consecutive `mid` values never more
    than 1.0 apart) — the "gap from yesterday's close" component of
    `true_range` never exceeds the bar's own 2.0 range, so its ATR settles on
    a constant 2.0 from the very first bar, not a decaying approximation of
    one. `typical = (H+L+C)/3` then collapses to exactly `mid`, which is what
    makes this series a hand-checkable bucket assignment rather than one that
    needs the kernel's own arithmetic trusted to build the fixture."""
    base = datetime(2026, 6, 1, tzinfo=UTC)
    times = [base + timedelta(minutes=i) for i in range(len(mid))]
    high = [m + 1.0 for m in mid]
    low = [m - 1.0 for m in mid]
    series = Series(
        open=np.array(mid, dtype=np.float64),
        high=np.array(high, dtype=np.float64),
        low=np.array(low, dtype=np.float64),
        close=np.array(mid, dtype=np.float64),
    )
    return series, times


# bucket_atr=0.5 × ATR=2.0 → bucket_width=1.0 — bucket `b` spans `[99 + b, 100 +
# b)` once `lowest=99` (`min(low)`, one below the series' own lowest `mid` of 100).
_MID = [100.0, 100.0, 100.0, 101.0, 101.0, 101.0, 101.0, 102.0, 102.0, 101.0]
_PARAMS = {"atr_period": 3, "bucket_atr": 0.5, "value_area_pct": 70.0}


class TestTimeProfile:
    def test_point_of_control_matches_a_hand_recount(self):
        # bucket 1 (mid=100): bars 0,1,2 → count 3
        # bucket 2 (mid=101): bars 3,4,5,6,9 → count 5 — the busiest
        # bucket 3 (mid=102): bars 7,8 → count 2
        series, times = _minute_series(_MID)
        entry = get("time_profile")
        levels = fn_of(entry, TimeProfile)(series, times, _PARAMS)

        poc = next(lvl for lvl in levels if lvl.label == "POC")
        assert poc.count == 5
        assert poc.price == pytest.approx(101.5)  # bucket 2's own midpoint

    def test_every_bucket_carries_its_own_count(self):
        series, times = _minute_series(_MID)
        entry = get("time_profile")
        levels = fn_of(entry, TimeProfile)(series, times, _PARAMS)

        buckets = sorted(
            ((lvl.price, lvl.count) for lvl in levels if lvl.label not in ("VAH", "VAL")),
        )
        expected = [(100.5, 3), (101.5, 5), (102.5, 2)]
        assert len(buckets) == len(expected)
        for (price, count), (want_price, want_count) in zip(buckets, expected, strict=True):
            assert price == pytest.approx(want_price)
            assert count == want_count
        assert sum(count for _price, count in buckets if count is not None) == len(_MID)

    def test_value_area_expands_from_the_poc_by_weight(self):
        # Target is 70% of 10 bars = 7; the POC alone (5) falls short, so the
        # heavier neighbour (bucket 1, weight 3) is pulled in over the
        # lighter one (bucket 3, weight 2) — 5 + 3 = 8 clears the target.
        series, times = _minute_series(_MID)
        entry = get("time_profile")
        levels = fn_of(entry, TimeProfile)(series, times, _PARAMS)

        vah = next(lvl for lvl in levels if lvl.label == "VAH")
        val = next(lvl for lvl in levels if lvl.label == "VAL")
        assert vah.price == pytest.approx(102.0)  # top of bucket 2, bucket 3 excluded
        assert val.price == pytest.approx(100.0)  # bottom of bucket 1, now included
        assert vah.count is None
        assert val.count is None

    def test_a_wider_value_area_pct_pulls_in_the_last_bucket_too(self):
        # 100% covers every bar, so the value area is now the whole populated
        # range: bucket 3 (the last one left out at 70%) joins bucket 1,
        # which was already in — the edges become the full range's own.
        series, times = _minute_series(_MID)
        entry = get("time_profile")
        params = {**_PARAMS, "value_area_pct": 100.0}
        levels = fn_of(entry, TimeProfile)(series, times, params)

        vah = next(lvl for lvl in levels if lvl.label == "VAH")
        val = next(lvl for lvl in levels if lvl.label == "VAL")
        assert vah.price == pytest.approx(103.0)  # top of bucket 3
        assert val.price == pytest.approx(100.0)  # bottom of bucket 1 — unchanged from 70%

    def test_a_flat_series_has_no_bucket_width_to_measure_and_answers_empty(self):
        # `high == low == close` throughout: true range, and so ATR, is
        # exactly zero — `_minute_series`' fixed ±1 spread does not apply
        # here on purpose, since that spread is itself what gives every other
        # test in this file a nonzero bucket width to bucket into.
        flat = np.full(5, 100.0)
        series = Series(open=flat, high=flat, low=flat, close=flat)
        base = datetime(2026, 6, 1, tzinfo=UTC)
        times = [base + timedelta(minutes=i) for i in range(5)]
        entry = get("time_profile")
        assert fn_of(entry, TimeProfile)(series, times, _PARAMS) == []

    def test_an_empty_series_answers_empty(self):
        entry = get("time_profile")
        empty = Series(
            open=np.array([]), high=np.array([]), low=np.array([]), close=np.array([])
        )
        assert fn_of(entry, TimeProfile)(empty, [], _PARAMS) == []
