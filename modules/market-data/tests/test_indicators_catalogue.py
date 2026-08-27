"""What the catalogue promises, checked against what it actually computes. Two failure modes: an entry
declaring a line its `compute` never produces, and an entry crossing into deciding."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest
from computers import LINE_ENTRIES, fn_of

from market_data.indicators.catalogue import CATALOGUE, IndicatorSpec, Lines, Series

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

    @pytest.mark.parametrize("entry", LINE_ENTRIES, ids=lambda e: e.id)
    def test_output_keys_match_declared_lines(self, entry: IndicatorSpec):
        params = _default_params(entry)
        result = fn_of(entry, Lines)(SERIES, params)
        assert set(result.keys()) == {line.key for line in entry.lines}

    @pytest.mark.parametrize("entry", LINE_ENTRIES, ids=lambda e: e.id)
    def test_every_line_has_the_series_length(self, entry: IndicatorSpec):
        params = _default_params(entry)
        result = fn_of(entry, Lines)(SERIES, params)
        for values in result.values():
            assert len(values) == N


class TestOnlyLinesEntriesDeclareLines:
    """The other half of "an entry declares a line its compute never produces": only a `Lines` computer
    produces the arrays a `LineSpec` names, and the checks above only run over entries that do."""

    def test_no_other_kind_of_entry_declares_a_line(self) -> None:
        offenders = [
            (entry.id, type(entry.computer).__name__)
            for entry in CATALOGUE
            if entry.lines and not isinstance(entry.computer, Lines)
        ]
        assert offenders == [], (
            f"{offenders} declare lines but do not compute any — a line the picker offers "
            "and the chart draws nothing for"
        )

    def test_every_lines_entry_declares_at_least_one(self) -> None:
        offenders = [entry.id for entry in LINE_ENTRIES if not entry.lines]
        assert offenders == [], (
            f"{offenders} compute lines and declare none, so nothing is published from "
            "what they compute"
        )


class TestCatalogueBoundary:
    """"Wskaźnik liczy się z jednej serii świec" and "Katalog mierzy, a nie orzeka" — checked once,
    across the whole catalogue, so a future entry cannot cross either line without this failing."""

    def test_no_entry_reads_volume(self):
        for entry in CATALOGUE:
            assert "volume" not in entry.inputs, entry.id

    def test_no_entry_takes_a_second_instrument(self):
        # A relational indicator would need a second symbol as an input or a param;
        # neither exists anywhere in this catalogue's shape today.
        for entry in CATALOGUE:
            assert not any("symbol" in p.name for p in entry.params), entry.id


class TestStartIndependence:
    """"Rozgrzewka jest wyliczona, jawna i niezależna od punktu startu" — the value for a given bar must
    not depend on how much history preceded the point a caller started reading from."""

    TAIL = 500

    @pytest.mark.parametrize(
        "entry", [e for e in LINE_ENTRIES if e.warmup.kind == "decay"], ids=lambda e: e.id
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

        long_result = fn_of(entry, Lines)(long_series, params)
        short_result = fn_of(entry, Lines)(short_series, params)

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
    """Every entry, at its default parameters, on the same committed series. A formula change shows up
    here as a diff, not as a chart that quietly draws something else."""

    @pytest.mark.parametrize("entry", LINE_ENTRIES, ids=lambda e: e.id)
    def test_default_params_match_the_committed_snapshot(self, entry: IndicatorSpec):
        golden = _load_golden()
        series = _golden_series(golden)
        params = _default_params(entry)
        result = fn_of(entry, Lines)(series, params)

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


class TestWarmupKindsAgree:
    """The wire declares exactly the warmup kinds the catalogue can produce. Written from a real
    divergence: `"anchored"` was declared, produced by nothing, and a `Literal` wider than reality refuses nothing."""

    @staticmethod
    def declared() -> set[str]:
        from typing import get_args

        from market_data.contract import IndicatorCatalogueEntryOut

        return set(get_args(IndicatorCatalogueEntryOut.model_fields["warmup_kind"].annotation))

    def test_every_declared_kind_is_producible_by_some_entry(self) -> None:
        produced = {entry.warmup.kind for entry in CATALOGUE}

        assert self.declared() <= produced, (
            f"the wire declares {sorted(self.declared() - produced)}, which no catalogue "
            "entry produces"
        )

    def test_every_kind_the_catalogue_produces_is_declared(self) -> None:
        produced = {entry.warmup.kind for entry in CATALOGUE}

        assert produced <= self.declared(), (
            f"the catalogue produces {sorted(produced - self.declared())}, which the wire "
            "does not declare — a response the module cannot validate"
        )
