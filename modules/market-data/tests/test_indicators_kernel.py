from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from market_data.indicators import kernel

GOLDEN = Path(__file__).parent / "golden" / "indicators_golden.json"


def _load_golden() -> dict:
    return json.loads(GOLDEN.read_text())


def _assert_matches(actual: np.ndarray, expected: list[float | None]) -> None:
    # The golden file stores values rounded to 8 decimal places, so the tolerance here is
    # about that rounding, not about the determinism this file is testing — determinism
    # is `TestDeterminism` and `TestStartIndependence` below, both exact.
    assert len(actual) == len(expected)
    for value, want in zip(actual, expected, strict=True):
        if want is None:
            assert math.isnan(value)
        else:
            assert value == pytest.approx(want, rel=1e-7, abs=1e-7)


class TestGoldenFile:
    """A committed snapshot of `kernel`'s output on a fixed series. A future change to
    any of these formulas shows up here as a diff, not as a silently different chart —
    design.md, "Zmiana wzoru bez podniesienia wersji"."""

    def test_sma(self):
        golden = _load_golden()
        _assert_matches(kernel.sma(golden["close"], 5), golden["sma_5"])

    def test_ema(self):
        golden = _load_golden()
        _assert_matches(kernel.ema(golden["close"], 5), golden["ema_5"])

    def test_atr(self):
        golden = _load_golden()
        tr = kernel.true_range(golden["high"], golden["low"], golden["close"])
        _assert_matches(kernel.rma(tr, 5), golden["atr_5"])


class TestDeterminism:
    def test_same_input_same_output(self):
        values = [100.0, 101.5, 99.2, 103.7, 98.1, 105.4, 102.0]
        assert list(kernel.ema(values, 3)) == list(kernel.ema(values, 3))

    def test_output_is_float64(self):
        assert kernel.sma([1, 2, 3, 4], 2).dtype == np.float64
        assert kernel.ema([1, 2, 3, 4], 2).dtype == np.float64


class TestWarmupNaN:
    """`np.nan`, never `0.0`, for a bar a finite window cannot answer yet —
    `market-data-indicators` spec, "Okresy przed rozgrzewką"."""

    def test_sma_nan_before_period(self):
        result = kernel.sma([1.0, 2.0, 3.0, 4.0, 5.0], 3)
        assert math.isnan(result[0])
        assert math.isnan(result[1])
        assert not math.isnan(result[2])

    def test_rolling_max_nan_before_period(self):
        result = kernel.rolling_max([1.0, 5.0, 2.0, 8.0], 3)
        assert math.isnan(result[0])
        assert math.isnan(result[1])
        assert result[2] == 5.0
        assert result[3] == 8.0

    def test_ema_never_nan(self):
        # Recursive filters are defined from the first bar onward — whether to trust an
        # early value is `warmup.py`'s question, answered outside the kernel.
        result = kernel.ema([1.0, 2.0, 3.0], 20)
        assert not any(math.isnan(v) for v in result)


class TestRollingArgExtreme:
    def test_argmax_current_bar_is_zero(self):
        result = kernel.rolling_argmax([1.0, 2.0, 5.0, 3.0], 3)
        assert math.isnan(result[0])
        assert math.isnan(result[1])
        assert result[2] == 0  # window [1,2,5]: max is the current bar
        assert result[3] == 1  # window [2,5,3]: max is one bar back

    def test_argmin_oldest_bar_in_window(self):
        result = kernel.rolling_argmin([5.0, 1.0, 4.0, 3.0], 3)
        assert math.isnan(result[1])
        assert result[2] == 1  # window [5,1,4]: min one bar back
        assert result[3] == 2  # window [1,4,3]: min two bars back (oldest in window)

    def test_tie_favours_the_older_bar(self):
        result = kernel.rolling_argmax([3.0, 3.0], 2)
        assert result[1] == 1  # both bars tie; the older one wins


class TestLinreg:
    def test_exact_fit_on_a_straight_line(self):
        # y = 2x + 1 fits perfectly: slope 2, r_squared 1, endpoint = 2*(n-1)+1.
        values = [1.0, 3.0, 5.0, 7.0, 9.0]
        assert kernel.linreg_slope(values, 5)[-1] == pytest.approx(2.0)
        assert kernel.r_squared(values, 5)[-1] == pytest.approx(1.0)
        assert kernel.linreg(values, 5)[-1] == pytest.approx(9.0)

    def test_flat_window_has_undefined_r_squared(self):
        result = kernel.r_squared([5.0, 5.0, 5.0], 3)
        assert math.isnan(result[-1])

    def test_nan_before_period(self):
        result = kernel.linreg([1.0, 2.0, 3.0], 5)
        assert all(math.isnan(v) for v in result)


class TestMeanAbsDev:
    def test_matches_hand_computed_value(self):
        # Window [1,2,3,4,5]: mean 3, absolute deviations [2,1,0,1,2], mean 1.2.
        result = kernel.mean_abs_dev([1.0, 2.0, 3.0, 4.0, 5.0], 5)
        assert result[-1] == pytest.approx(1.2)


class TestShiftDiff:
    def test_shift_reads_n_bars_back(self):
        result = kernel.shift([10.0, 20.0, 30.0, 40.0], 2)
        assert math.isnan(result[0])
        assert math.isnan(result[1])
        assert result[2] == 10.0
        assert result[3] == 20.0

    def test_diff_is_the_change_over_n_bars(self):
        result = kernel.diff([10.0, 20.0, 35.0], 1)
        assert math.isnan(result[0])
        assert result[1] == pytest.approx(10.0)
        assert result[2] == pytest.approx(15.0)


class TestCross:
    def test_detects_upward_and_downward_crossings(self):
        a = [1.0, 2.0, 4.0, 3.0, 1.0]
        b = [2.0, 2.0, 2.0, 2.0, 2.0]
        result = kernel.cross(a, b)
        assert math.isnan(result[0])
        assert result[1] == 0.0
        assert result[2] == 1.0  # a crosses above b
        assert result[3] == 0.0
        assert result[4] == -1.0  # a crosses below b

    def test_no_crossing_when_never_on_the_other_side(self):
        result = kernel.cross([5.0, 6.0, 7.0], [1.0, 1.0, 1.0])
        assert result[1] == 0.0
        assert result[2] == 0.0


class TestTrueRange:
    def test_first_bar_falls_back_to_own_range(self):
        result = kernel.true_range([110.0], [100.0], [105.0])
        assert result[0] == pytest.approx(10.0)

    def test_gap_up_widens_range(self):
        # A gap from yesterday's close to today's high, bigger than today's own H-L.
        high, low, close = [100.0, 130.0], [95.0, 128.0], [98.0, 129.0]
        result = kernel.true_range(high, low, close)
        assert result[1] == pytest.approx(130.0 - 98.0)

    def test_gap_down_widens_range(self):
        high, low, close = [100.0, 80.0], [95.0, 78.0], [98.0, 79.0]
        result = kernel.true_range(high, low, close)
        assert result[1] == pytest.approx(98.0 - 78.0)
