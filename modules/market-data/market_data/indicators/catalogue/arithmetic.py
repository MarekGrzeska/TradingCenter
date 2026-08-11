"""Two numeric helpers more than one group needs.

Small enough to have been a private function in whichever module used it first, and it
was — until the second and third group wanted the same `nan`-safe division. Here rather
than in `kernel.py`, which is the deliberately closed set of ~20 primitives every
indicator is built from; these two are neither primitives nor indicators.
"""

from __future__ import annotations

import numpy as np


def safe_divide(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    """`numerator / denominator`, `np.nan` where undefined instead of a runtime
    warning — division by a zero high-low range or a flat window is a property of
    the data (a single-tick candle, an illiquid pair), not a bug in the formula."""
    with np.errstate(invalid="ignore", divide="ignore"):
        return numerator / denominator


LN2 = float(np.log(2.0))
