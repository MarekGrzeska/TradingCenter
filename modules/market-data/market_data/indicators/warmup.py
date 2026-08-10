"""How far back a recursive filter needs to be read before its answer can be trusted.

The rule (docs/wskazniki-techniczne.html, "Co znaczy deterministycznie"): a first-order
filter with decay `alpha` weighs its seed sample `(1 - alpha) ** m` after `m` bars. Read
enough bars that the weight of the seed falls below `epsilon` and the seed — which is the
one thing that would otherwise differ between "computed from January" and "computed from
March" — no longer moves the answer by more than the precision anyone reads a price at.

A finite window (`sma`, `wma`, `stdev`, the two rolling extremes) has no such question:
its answer is already independent of anything before the window, so its warmup is exactly
its period, not an approximation of one.
"""

from __future__ import annotations

import math

# Below the precision anyone reads a price or an oscillator at. Not a knob: raising it
# shortens warmup at the cost of the seed still being visible in the answer, which is the
# one thing this whole scheme exists to make negligible.
EPSILON = 1e-9


def decay_warmup_bars(alpha: float, epsilon: float = EPSILON) -> int:
    """`m` such that `(1 - alpha) ** m < epsilon`."""
    if not 0 < alpha <= 1:
        raise ValueError(f"alpha must be in (0, 1]; got {alpha!r}")
    if alpha == 1:
        return 1
    return math.ceil(math.log(epsilon) / math.log(1 - alpha))


def ema_warmup_bars(period: int) -> int:
    return decay_warmup_bars(2.0 / (period + 1))


def rma_warmup_bars(period: int) -> int:
    return decay_warmup_bars(1.0 / period)
