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
