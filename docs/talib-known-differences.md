# TA-Lib as a test oracle: the written list of known differences

Task 2.11, `design.md`'s "Własne jądro na `numpy`, TA-Lib wyłącznie jako wyrocznia testowa".
TA-Lib is a dev-only dependency, nothing in `market_data.indicators` imports it, and its only
job is to answer "does an independent implementation agree with this formula".
The comparison itself is `modules/market-data/tests/test_indicators_talib_comparison.py`.

## What is not compared, and why

**No TA-Lib equivalent at all:** `atr_pct`, `bar_range_atr`, `body_ratio`, `wick_up_ratio`,
`wick_down_ratio`, `close_position`, `gap_prev_close_atr`, `range_position`, `zscore`, `stdev`
(as its own entry), `parkinson`, `garman_klass`, `rogers_satchell`, `yang_zhang`, `ulcer`,
`choppiness`, `vortex`, `r_squared`, `rma` (as its own entry — TA-Lib never exposes Wilder's
smoothing standalone, only baked into `ATR`/`RSI`/`ADX`), `hma`, `alma`, `bbands_percent_b`,
`bbands_bandwidth`, `keltner`, `donchian`, `envelope`.

None of this is a gap in either implementation. It is exactly the curated set `proposal.md`
describes, which a narrower, older library never had reason to carry.

**`stoch_rsi`.** TA-Lib's `STOCHRSI` returns the *raw* stochastic of RSI — `fastk`/`fastd` —
with no `slowk`-style smoothing stage before the `%D` average. This catalogue's `stoch_rsi`
smooths `%K` first (`k_smooth`), the same shape `stoch` itself uses. The two answer
differently-defined questions rather than disagreeing about the same one.

**`cmo`.** Chande's original 1994 definition sums gains and losses over a plain trailing window,
which is what this catalogue computes. TA-Lib's `CMO` instead reuses Wilder's recursive smoothing
from `RSI` — verified numerically to equal `2 * RSI - 100` bit for bit, which is not an
independent formula at all, only a rescaling of `RSI`. Kept as the textbook definition rather
than matched to TA-Lib's redundant-with-RSI one.

## Seed differences, not bugs on either side

TA-Lib seeds `EMA`-family recursive filters with a plain average of the first `period` bars.
This module seeds with the first bar itself, and instead guarantees through `warmup.py` that the
seed's influence has decayed below `1e-9` by the time `warmup_bars` bars have passed.

Comparing only the last `TAIL` bars of an `N`-bar series, well past every entry's own warmup, is
what makes the comparison test the *formula* instead of re-measuring the seed.

## One real bug this found

`aroon` originally read a `period`-bar window, which can never report "the extreme is today"
(`bars_since == 0` is unreachable). TA-Lib — and Chande's original definition — read `period + 1`
bars, counting today as day zero. Fixed in `catalogue/regime.py`; the two now agree to float
precision. It is the reason task 2.11 is worth doing even when most of it is "no equivalent
exists".
