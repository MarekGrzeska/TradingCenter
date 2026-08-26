"""How far back a recursive filter must be read before its answer can be trusted: enough bars that
the seed's weight falls below epsilon. A finite window has no such question — its warmup is its period."""

from __future__ import annotations

import math

# Below the precision anyone reads a price or an oscillator at. Not a knob: raising it shortens
# warmup at the cost of the seed still being visible in the answer.
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


def kama_warmup_bars(period: int, slow: int) -> int:
    """`period` bars for the efficiency ratio's own window, plus the decay warmup of `kama`'s slowest
    possible smoothing constant — see `kernel.kama` for why that is a safe upper bound."""
    return period + decay_warmup_bars(2.0 / (slow + 1))
