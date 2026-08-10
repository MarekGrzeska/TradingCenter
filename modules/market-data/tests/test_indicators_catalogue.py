"""What the catalogue promises, checked against what it actually computes.

Two failure modes this file exists for, both named in `CLAUDE.md`'s "A new field on
market-data's wire" and `design.md`'s risk list:

- An entry declares a line its `compute` never produces (or produces one it never
  declared) — nothing about Python or FastAPI catches that on its own.
- An entry crosses into orzekanie: a boolean output, a volume input, a second
  instrument. `market-data-indicators` spec, "Katalog mierzy, a nie orzeka" and "Wskaźnik
  liczy się z jednej serii świec".
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from market_data.indicators.catalogue import CATALOGUE, IndicatorSpec, Series

N = 4000
GOLDEN = Path(__file__).parent / "golden" / "indicators_golden.json"


def _synthetic_series(n: int) -> Series:
    """A deterministic, arbitrary-looking OHLC series — no formula here means
    anything, only that it is the same series every time this file runs."""
    i = np.arange(n, dtype=np.float64)
    close = 100 + 8 * np.sin(i / 37) + 0.01 * i + 3 * np.sin(i / 5.3)
    spread = 0.4 + 0.15 * np.abs(np.sin(i / 11))
    high = close + spread
    low = close - spread
    open_ = close - 0.3 * np.sin(i / 2.7)
    return Series(open=open_, high=high, low=low, close=close)


SERIES = _synthetic_series(N)


def _default_params(entry: IndicatorSpec) -> dict[str, float]:
    return {p.name: p.default for p in entry.params}


class TestCatalogueMatchesKernel:
    """Every entry, computed once on a shared series, checked against its own
    declaration — the test 1.15 calls for in tasks.md."""

    @pytest.mark.parametrize("entry", CATALOGUE, ids=lambda e: e.id)
    def test_output_keys_match_declared_lines(self, entry: IndicatorSpec):
        params = _default_params(entry)
        result = entry.compute(SERIES, params)
        assert set(result.keys()) == {line.key for line in entry.lines}

    @pytest.mark.parametrize("entry", CATALOGUE, ids=lambda e: e.id)
    def test_every_line_has_the_series_length(self, entry: IndicatorSpec):
        params = _default_params(entry)
        result = entry.compute(SERIES, params)
        for values in result.values():
            assert len(values) == N

    @pytest.mark.parametrize("entry", CATALOGUE, ids=lambda e: e.id)
    def test_output_is_numeric_float(self, entry: IndicatorSpec):
        params = _default_params(entry)
        result = entry.compute(SERIES, params)
        for values in result.values():
            assert values.dtype == np.float64


class TestCatalogueBoundary:
    """`market-data-indicators` spec, "Wskaźnik liczy się z jednej serii świec" and
    "Katalog mierzy, a nie orzeka" — checked once, across the whole catalogue, so a
    future entry cannot cross either line without this failing."""

    def test_no_entry_reads_volume(self):
        for entry in CATALOGUE:
            assert "volume" not in entry.inputs, entry.id

    def test_no_entry_takes_a_second_instrument(self):
        # A relational wskaźnik would need a second symbol as an input or a param;
        # neither exists anywhere in this catalogue's shape today.
        for entry in CATALOGUE:
            assert not any("symbol" in p.name for p in entry.params), entry.id

    def test_no_param_is_boolean(self):
        for entry in CATALOGUE:
            for param in entry.params:
                assert param.type in ("int", "float"), (entry.id, param.name)

    @pytest.mark.parametrize("entry", CATALOGUE, ids=lambda e: e.id)
    def test_output_values_are_not_boolean(self, entry: IndicatorSpec):
        params = _default_params(entry)
        result = entry.compute(SERIES, params)
        for values in result.values():
            assert values.dtype != np.bool_


class TestStartIndependence:
    """`market-data-indicators` spec, "Rozgrzewka jest wyliczona, jawna i niezależna od
    punktu startu" — the value for a given bar must not depend on how much history
    preceded the point a caller happened to start reading from.
    """

    TAIL = 500

    @pytest.mark.parametrize(
        "entry", [e for e in CATALOGUE if e.warmup.kind == "decay"], ids=lambda e: e.id
    )
    def test_tail_matches_regardless_of_where_the_read_started(self, entry: IndicatorSpec):
        params = _default_params(entry)
        m = entry.warmup_bars(params)

        long_series = SERIES
        short_start = N - (self.TAIL + m)
        short_series = Series(
            open=SERIES.open[short_start:],
            high=SERIES.high[short_start:],
            low=SERIES.low[short_start:],
            close=SERIES.close[short_start:],
        )

        long_result = entry.compute(long_series, params)
        short_result = entry.compute(short_series, params)

        for key in long_result:
            long_tail = long_result[key][-self.TAIL :]
            short_tail = short_result[key][-self.TAIL :]
            for a, b in zip(long_tail, short_tail, strict=True):
                assert not math.isnan(a) and not math.isnan(b), (entry.id, key)
                assert a == pytest.approx(b, rel=1e-9, abs=1e-9), (entry.id, key)


def _load_golden() -> dict:
    return json.loads(GOLDEN.read_text())


def _golden_series(golden: dict) -> Series:
    return Series(
        open=np.array(golden["open"], dtype=np.float64),
        high=np.array(golden["high"], dtype=np.float64),
        low=np.array(golden["low"], dtype=np.float64),
        close=np.array(golden["close"], dtype=np.float64),
    )


class TestCatalogueGoldenFile:
    """Task 2.10's "pliki wzorcowe dla całego zestawu" — every entry, at its
    default parameters, on the same committed series `test_indicators_kernel.py`
    already golden-tests `sma`/`ema`/`atr` against (with an added `open` column,
    absent from that file until now because nothing in etap zero read it). A
    formula change shows up here as a diff, not as a chart that quietly draws
    something else (design.md, "Zmiana wzoru bez podniesienia wersji")."""

    @pytest.mark.parametrize("entry", CATALOGUE, ids=lambda e: e.id)
    def test_default_params_match_the_committed_snapshot(self, entry: IndicatorSpec):
        golden = _load_golden()
        series = _golden_series(golden)
        params = _default_params(entry)
        result = entry.compute(series, params)

        for line in entry.lines:
            key = f"{entry.id}_{line.key}"
            assert key in golden, f"golden file has no {key!r} — regenerate it for this entry"
            expected = golden[key]
            actual = result[line.key]
            assert len(actual) == len(expected)
            for value, want in zip(actual, expected, strict=True):
                if want is None:
                    assert math.isnan(value), (entry.id, line.key)
                else:
                    assert value == pytest.approx(want, rel=1e-7, abs=1e-7), (entry.id, line.key)
