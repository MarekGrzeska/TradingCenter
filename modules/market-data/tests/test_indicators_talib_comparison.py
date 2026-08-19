"""Cross-checked against TA-Lib — task 2.11, design.md's "Własne jądro na `numpy`,
TA-Lib wyłącznie jako wyrocznia testowa": TA-Lib is a dev-only dependency, nothing
in `market_data.indicators` imports it, and its only job is to answer the
question "does an independent implementation agree with this formula".

**What is not compared here, and why — the "spisana lista znanych różnic":**

- No TA-Lib equivalent at all: `atr_pct`, `bar_range_atr`, `body_ratio`,
  `wick_up_ratio`, `wick_down_ratio`, `close_position`, `gap_prev_close_atr`,
  `range_position`, `zscore`, `stdev` (as its own entry), `parkinson`,
  `garman_klass`, `rogers_satchell`, `yang_zhang`, `ulcer`, `choppiness`,
  `vortex`, `r_squared`, `rma` (as its own entry — TA-Lib never exposes Wilder's
  smoothing standalone, only baked into `ATR`/`RSI`/`ADX`), `hma`, `alma`,
  `bbands_percent_b`, `bbands_bandwidth`, `keltner`, `donchian`, `envelope`.
  None of this is a gap in either implementation — it is exactly the curated
  set proposal.md describes that a narrower, older library never had reason to
  carry.
- `stoch_rsi`: TA-Lib's `STOCHRSI` returns the *raw* stochastic of RSI —
  `fastk`/`fastd` — with no `slowk`-style smoothing stage before the `%D`
  average. This catalogue's `stoch_rsi` smooths `%K` first (`k_smooth`), the
  same shape `stoch` itself uses. The two are answering differently-defined
  questions, not disagreeing about the same one.
- `cmo`: Chande's original 1994 definition sums gains and losses over a plain
  trailing window (what this catalogue computes). TA-Lib's `CMO` instead reuses
  Wilder's recursive smoothing from `RSI` — verified numerically here to equal
  `2 * RSI - 100` bit for bit, which is not an independent formula at all, only
  a rescaling of `RSI`. Kept as the textbook definition rather than matched to
  TA-Lib's redundant-with-RSI one.

**Seed differences, not bugs on either side** (the reason for comparing only a
long series' tail rather than a fresh one bar by bar): TA-Lib seeds `EMA`
family recursive filters with a plain average of the first `period` bars; this
module seeds with the first bar itself and instead guarantees via
`warmup.py` that the seed's influence has decayed below `1e-9` by the time
`warmup_bars` bars have passed. Comparing only the last `TAIL` bars of a
`N`-bar series, well past every entry's own warmup, is what makes the
comparison test the *formula* instead of re-measuring the seed.

**One real bug this file found**: `aroon` originally read a `period`-bar
window, which can never report "the extreme is today" (`bars_since == 0` is
unreachable). TA-Lib — and Chande's original definition — read `period + 1`
bars, counting today as day zero. Fixed in `catalogue/regime.py`; the two now agree
to float precision. Left in this file's history as the reason task 2.11 is
worth doing even when most of it is "no equivalent exists".
"""

from __future__ import annotations

import numpy as np
import pytest

talib = pytest.importorskip("talib", reason="TA-Lib is a dev-only comparison oracle")

from computers import fn_of

from market_data.indicators.catalogue import Lines, get

N = 2000
TAIL = 300


def _series():
    from market_data.indicators.catalogue import Series

    i = np.arange(N, dtype=np.float64)
    close = 100 + 8 * np.sin(i / 37) + 0.01 * i + 3 * np.sin(i / 5.3)
    spread = 0.4 + 0.15 * np.abs(np.sin(i / 11))
    high = close + spread
    low = close - spread
    open_ = close - 0.3 * np.sin(i / 2.7)
    return Series(open=open_, high=high, low=low, close=close), open_, high, low, close


SERIES, OPEN, HIGH, LOW, CLOSE = _series()


def _assert_tail_matches(ours: np.ndarray, theirs: np.ndarray, label: str, tol: float = 1e-6) -> None:
    a = np.asarray(ours[-TAIL:], dtype=np.float64)
    b = np.asarray(theirs[-TAIL:], dtype=np.float64)
    assert not np.any(np.isnan(a)), f"{label}: our tail has NaN — warmup should have settled by now"
    assert not np.any(np.isnan(b)), f"{label}: TA-Lib's tail has NaN"
    diff = np.abs(a - b)
    scale = np.maximum(np.abs(b), 1.0)
    assert np.all(diff / scale < tol), f"{label}: max relative diff {np.max(diff / scale):.3e}"


class TestAgainstTalib:
    def test_sma(self):
        r = fn_of(get("sma"), Lines)(SERIES, {"period": 20})
        _assert_tail_matches(r["sma"], talib.SMA(CLOSE, 20), "sma")

    def test_ema(self):
        r = fn_of(get("ema"), Lines)(SERIES, {"period": 20})
        _assert_tail_matches(r["ema"], talib.EMA(CLOSE, 20), "ema")

    def test_wma(self):
        r = fn_of(get("wma"), Lines)(SERIES, {"period": 20})
        _assert_tail_matches(r["wma"], talib.WMA(CLOSE, 20), "wma")

    def test_kama(self):
        # TA-Lib's KAMA hardcodes fast=2/slow=30 internally — matched here rather
        # than left at this catalogue's own defaults (fast=2, slow=30, period=10),
        # which happen to already agree.
        r = fn_of(get("kama"), Lines)(SERIES, {"period": 10, "fast": 2, "slow": 30})
        _assert_tail_matches(r["kama"], talib.KAMA(CLOSE, 10), "kama")

    def test_lsma_against_linearreg(self):
        r = fn_of(get("lsma"), Lines)(SERIES, {"period": 20})
        _assert_tail_matches(r["lsma"], talib.LINEARREG(CLOSE, 20), "lsma vs LINEARREG")

    def test_linreg_slope(self):
        r = fn_of(get("linreg_slope"), Lines)(SERIES, {"period": 14})
        _assert_tail_matches(
            r["linreg_slope"], talib.LINEARREG_SLOPE(CLOSE, 14), "linreg_slope", tol=1e-4
        )

    def test_atr(self):
        r = fn_of(get("atr"), Lines)(SERIES, {"period": 14})
        _assert_tail_matches(r["atr"], talib.ATR(HIGH, LOW, CLOSE, 14), "atr")

    def test_atr_pct(self):
        # Not a TA-Lib function of its own — `atr / close * 100`, checked against
        # TA-Lib's own ATR run through that same, trivial arithmetic.
        r = fn_of(get("atr_pct"), Lines)(SERIES, {"period": 14})
        expected = 100 * talib.ATR(HIGH, LOW, CLOSE, 14) / CLOSE
        _assert_tail_matches(r["atr_pct"], expected, "atr_pct")

    def test_rsi(self):
        r = fn_of(get("rsi"), Lines)(SERIES, {"period": 14})
        _assert_tail_matches(r["rsi"], talib.RSI(CLOSE, 14), "rsi")

    def test_macd(self):
        r = fn_of(get("macd"), Lines)(SERIES, {"fast_period": 12, "slow_period": 26, "signal_period": 9})
        macd, signal, hist = talib.MACD(CLOSE, 12, 26, 9)
        _assert_tail_matches(r["macd"], macd, "macd.macd")
        _assert_tail_matches(r["signal"], signal, "macd.signal")
        _assert_tail_matches(r["histogram"], hist, "macd.histogram")

    def test_stoch(self):
        r = fn_of(get("stoch"), Lines)(SERIES, {"k_period": 14, "k_smooth": 3, "d_period": 3})
        k, d = talib.STOCH(
            HIGH, LOW, CLOSE, fastk_period=14, slowk_period=3, slowk_matype=0, slowd_period=3, slowd_matype=0
        )
        _assert_tail_matches(r["k"], k, "stoch.k")
        _assert_tail_matches(r["d"], d, "stoch.d")

    def test_cci(self):
        r = fn_of(get("cci"), Lines)(SERIES, {"period": 20})
        _assert_tail_matches(r["cci"], talib.CCI(HIGH, LOW, CLOSE, 20), "cci", tol=1e-4)

    def test_roc(self):
        r = fn_of(get("roc"), Lines)(SERIES, {"period": 9})
        _assert_tail_matches(r["roc"], talib.ROC(CLOSE, 9), "roc")

    def test_williams_r(self):
        r = fn_of(get("williams_r"), Lines)(SERIES, {"period": 14})
        _assert_tail_matches(r["williams_r"], talib.WILLR(HIGH, LOW, CLOSE, 14), "williams_r")

    def test_adx_and_directional_indicators(self):
        r = fn_of(get("adx"), Lines)(SERIES, {"period": 14})
        _assert_tail_matches(r["adx"], talib.ADX(HIGH, LOW, CLOSE, 14), "adx")
        _assert_tail_matches(r["plus_di"], talib.PLUS_DI(HIGH, LOW, CLOSE, 14), "plus_di")
        _assert_tail_matches(r["minus_di"], talib.MINUS_DI(HIGH, LOW, CLOSE, 14), "minus_di")

    def test_aroon(self):
        r = fn_of(get("aroon"), Lines)(SERIES, {"period": 14})
        aroon_down, aroon_up = talib.AROON(HIGH, LOW, 14)
        _assert_tail_matches(r["aroon_up"], aroon_up, "aroon_up")
        _assert_tail_matches(r["aroon_down"], aroon_down, "aroon_down")

    def test_bbands(self):
        r = fn_of(get("bbands"), Lines)(SERIES, {"period": 20, "mult": 2.0})
        upper, basis, lower = talib.BBANDS(CLOSE, 20, 2.0, 2.0, 0)
        _assert_tail_matches(r["upper"], upper, "bbands.upper")
        _assert_tail_matches(r["basis"], basis, "bbands.basis")
        _assert_tail_matches(r["lower"], lower, "bbands.lower")


class TestKnownDifferenceIsDocumentedNotGuessed:
    """Pins the one claim the module docstring makes about `cmo`, so a future
    TA-Lib upgrade that changes its behaviour is caught here rather than only
    in a comment nobody re-reads."""

    def test_talib_cmo_is_exactly_rescaled_rsi(self):
        period = 14
        rsi = talib.RSI(CLOSE, period)
        cmo = talib.CMO(CLOSE, period)
        diff = np.abs((2 * rsi - 100) - cmo)
        assert np.nanmax(diff) < 1e-9
