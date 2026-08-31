"""`market-data-indicators`, "Punkt zwrotny potwierdza się z opóźnieniem" and "Poziomy z wyższego
interwału pochodzą z zamkniętego okresu" — small, hand-computed series, not the golden synthetic one."""

from __future__ import annotations

import math

import numpy as np
import pytest
from computers import fn_of

from market_data.indicators.catalogue import (
    ClusterLevels,
    HtfLevels,
    Lines,
    Markers,
    Series,
    get,
)

# A high series with two unambiguous swing highs (n=2), at index 2 and index 7.
_HIGH = [1.0, 2.0, 5.0, 2.0, 1.0, 1.0, 2.0, 7.0, 2.0, 1.0]
# A low series with two unambiguous swing lows (n=2), at the same two indices —
# coincidence, not a rule; it only keeps one series doing double duty in the tests.
_LOW = [10.0, 9.0, 3.0, 9.0, 10.0, 10.0, 9.0, 1.0, 9.0, 10.0]


def _structure_series(n: int = 10) -> Series:
    high = np.array(_HIGH[:n], dtype=np.float64)
    low = np.array(_LOW[:n], dtype=np.float64)
    close = (high + low) / 2
    open_ = close.copy()
    return Series(open=open_, high=high, low=low, close=close)


class TestSwingPoints:
    def test_confirmed_swing_highs_and_lows(self):
        entry = get("swing_points")
        series = _structure_series()
        points = fn_of(entry, Markers)(series, {"n": 2})

        highs = {p.bar: p.price for p in points if p.label == "Swing High"}
        lows = {p.bar: p.price for p in points if p.label == "Swing Low"}
        assert highs == {2: 5.0, 7: 7.0}
        assert lows == {2: 3.0, 7: 1.0}

    def test_too_short_a_series_confirms_nothing(self):
        entry = get("swing_points")
        series = _structure_series(4)  # shorter than 2n+1 = 5
        assert fn_of(entry, Markers)(series, {"n": 2}) == []

    def test_stays_the_same_on_a_longer_read(self):
        """Task 3.10: a turning point neither disappears nor moves when the same stretch is read again
        inside a longer series — the guarantee that lets a consumer trust a swing point it drew."""
        entry = get("swing_points")
        short_series = _structure_series(9)  # just enough to confirm bar 2, not bar 7
        long_series = _structure_series(10)

        short_points = {
            (p.bar, p.label): p.price for p in fn_of(entry, Markers)(short_series, {"n": 2})
        }
        long_points = {
            (p.bar, p.label): p.price for p in fn_of(entry, Markers)(long_series, {"n": 2})
        }

        for key, price in short_points.items():
            assert long_points[key] == price


class TestLastSwing:
    def test_steps_at_confirmation_not_at_the_extreme(self):
        entry = get("last_swing_high")
        series = _structure_series()
        result = fn_of(entry, Lines)(series, {"n": 2})["last_swing_high"]

        # The extreme sits at bar 2; confirmation (n=2 bars later) lands at bar 4.
        for i in range(4):
            assert math.isnan(result[i])
        for i in range(4, 9):
            assert result[i] == pytest.approx(5.0)
        assert result[9] == pytest.approx(7.0)

    def test_last_swing_low_mirrors_last_swing_high(self):
        entry = get("last_swing_low")
        series = _structure_series()
        result = fn_of(entry, Lines)(series, {"n": 2})["last_swing_low"]

        for i in range(4):
            assert math.isnan(result[i])
        for i in range(4, 9):
            assert result[i] == pytest.approx(3.0)
        assert result[9] == pytest.approx(1.0)

    def test_no_gap_once_confirmed(self):
        """`design.md`'s E2 acceptance bullet: `last_swing_high` is a line without
        holes after its first confirmation."""
        entry = get("last_swing_high")
        series = _structure_series()
        result = fn_of(entry, Lines)(series, {"n": 2})["last_swing_high"]
        assert not any(math.isnan(v) for v in result[4:])


class TestRollingExtreme:
    def test_matches_rolling_max_and_min(self):
        entry = get("rolling_extreme")
        series = _structure_series()
        result = fn_of(entry, Lines)(series, {"n": 3})
        assert result["upper"][-1] == max(_HIGH[7:10])
        assert result["lower"][-1] == min(_LOW[7:10])


class TestLevelClusters:
    def test_two_equal_highs_within_tolerance_form_one_cluster(self):
        # Two swing highs a hair apart, confirmed with n=2; ATR(2) on this series is
        # wide enough that a generous tol groups them into one cluster of weight 2.
        high = [1.0, 2.0, 10.0, 2.0, 1.0, 1.0, 2.0, 10.2, 2.0, 1.0]
        low = [0.0, 0.5, 0.5, 0.5, 0.0, 0.0, 0.5, 0.5, 0.5, 0.0]
        close = [(h + lo) / 2 for h, lo in zip(high, low, strict=True)]
        series = Series(
            open=np.array(close, dtype=np.float64),
            high=np.array(high, dtype=np.float64),
            low=np.array(low, dtype=np.float64),
            close=np.array(close, dtype=np.float64),
        )
        entry = get("level_clusters")
        clusters = fn_of(entry, ClusterLevels)(series, {"n": 2, "tol": 2.0, "atr_period": 2})

        equal_highs = [c for c in clusters if c.label == "Equal High"]
        assert len(equal_highs) == 1
        assert equal_highs[0].count == 2
        assert equal_highs[0].price == pytest.approx((10.0 + 10.2) / 2)

    def test_zero_tolerance_never_clusters(self):
        series = _structure_series()
        entry = get("level_clusters")
        clusters = fn_of(entry, ClusterLevels)(series, {"n": 2, "tol": 0.0, "atr_period": 2})
        assert clusters == []


class TestPivots:
    """Round numbers, hand-computed — `docs/wskazniki-plan-wdrozenia.html` calls
    every one of these "arytmetyka na jednej świecy, zero uznaniowości"."""

    OHLC = (10.0, 20.0, 10.0, 15.0)  # open, high, low, close

    def _levels(self, indicator_id: str) -> dict[str, float]:
        entry = get(indicator_id)
        return {level.label: level.price for level in fn_of(entry, HtfLevels)(self.OHLC)}

    def test_classic(self):
        levels = self._levels("pivots_classic")
        assert levels["PP"] == pytest.approx(15.0)
        assert levels["R1"] == pytest.approx(20.0)
        assert levels["S1"] == pytest.approx(10.0)
        assert levels["R2"] == pytest.approx(25.0)
        assert levels["S2"] == pytest.approx(5.0)
        assert levels["R3"] == pytest.approx(30.0)
        assert levels["S3"] == pytest.approx(0.0)

    def test_fibonacci(self):
        levels = self._levels("pivots_fibonacci")
        assert levels["PP"] == pytest.approx(15.0)
        assert levels["R1"] == pytest.approx(18.82)
        assert levels["S1"] == pytest.approx(11.18)
        assert levels["R2"] == pytest.approx(21.18)
        assert levels["S2"] == pytest.approx(8.82)

    def test_camarilla(self):
        levels = self._levels("pivots_camarilla")
        assert levels["R4"] == pytest.approx(20.5)
        assert levels["R1"] == pytest.approx(15.91666667)
        assert levels["S1"] == pytest.approx(14.08333333)
        assert levels["S4"] == pytest.approx(9.5)

    def test_woodie(self):
        levels = self._levels("pivots_woodie")
        assert levels["PP"] == pytest.approx(15.0)
        assert levels["R1"] == pytest.approx(20.0)
        assert levels["S1"] == pytest.approx(10.0)

    def test_demark_close_above_open(self):
        levels = self._levels("pivots_demark")
        assert levels["PP"] == pytest.approx(16.25)
        assert levels["R1"] == pytest.approx(22.5)
        assert levels["S1"] == pytest.approx(12.5)

    def test_demark_switches_formula_on_close_below_open(self):
        # close < open now: x = H + 2L + C = 20 + 20 + 5 = 45.
        levels = self._levels_for("pivots_demark", (10.0, 20.0, 10.0, 5.0))
        assert levels["PP"] == pytest.approx(11.25)

    def _levels_for(
        self, indicator_id: str, ohlc: tuple[float, float, float, float]
    ) -> dict[str, float]:
        entry = get(indicator_id)
        return {level.label: level.price for level in fn_of(entry, HtfLevels)(ohlc)}
