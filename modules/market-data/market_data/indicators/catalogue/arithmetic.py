"""Two numeric helpers more than one group needs. Here rather than in `kernel.py`, which is the
closed set of primitives every indicator is built from; these two are neither."""

from __future__ import annotations

import numpy as np


def safe_divide(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    """`numerator / denominator`, `np.nan` where undefined: division by a zero range is a property
    of the data — a single-tick candle, an illiquid pair — not a bug in the formula."""
    with np.errstate(invalid="ignore", divide="ignore"):
        return numerator / denominator


LN2 = float(np.log(2.0))
