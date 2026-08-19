"""How much of the read range's own time each price bucket held.

A TPO reading, not a volume profile: this archive's volume is not reliably populated for
a CFD provider, so the weight is time (`market-data-indicators` spec, "Profil czasowy
liczy udział czasu, nie wolumenu").
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

import numpy as np

from .. import kernel
from .spec import IndicatorSpec, Param, ProfileLevel, Render, Series, TimeProfile, Warmup


def _time_profile_levels(
    s: Series, times: Sequence[datetime], p: Mapping[str, float]
) -> list[ProfileLevel]:
    """Buckets each minute bar by its typical price `(H+L+C)/3` into a bucket
    `bucket_atr` fractions of ATR wide — resolving design.md's open question in
    favour of an ATR fraction, the same unit `level_clusters`' tolerance
    already uses, over a fixed multiple of the instrument's own tick step this
    module has no per-instrument table for. One bar, one bucket: splitting a
    bar's own high-low range across every bucket it touches is a legitimate
    reading too, but this one is the one a hand recount of a small sample can
    actually check (task 5.5), which a fractional split cannot promise.

    The point of control is the single busiest bucket; the value area expands
    outward from it, always into whichever open neighbour currently holds
    more, until it covers `value_area_pct` of the bars read — the standard
    TPO rule, weighed by bar count in place of traded size.
    """
    n = len(s)
    if n == 0:
        return []

    atr_period = int(p["atr_period"])
    bucket_atr = float(p["bucket_atr"])
    value_area_pct = float(p["value_area_pct"])

    atr = kernel.rma(kernel.true_range(s.high, s.low, s.close), atr_period)
    reference_atr = float(atr[-1])
    bucket_width = bucket_atr * reference_atr
    if not bucket_width > 0:
        return []

    typical = (s.high + s.low + s.close) / 3
    lowest = float(np.min(s.low))
    bucket_of = np.floor((typical - lowest) / bucket_width).astype(np.int64)

    counts: dict[int, int] = {}
    for bucket in bucket_of:
        counts[int(bucket)] = counts.get(int(bucket), 0) + 1

    total = sum(counts.values())
    poc_bucket = max(counts, key=lambda b: (counts[b], -b))

    included_low = included_high = poc_bucket
    accumulated = counts[poc_bucket]
    target = total * value_area_pct / 100
    while accumulated < target:
        below, above = included_low - 1, included_high + 1
        gain_below, gain_above = counts.get(below, 0), counts.get(above, 0)
        if gain_below == 0 and gain_above == 0:
            break
        if gain_below >= gain_above:
            included_low, accumulated = below, accumulated + gain_below
        else:
            included_high, accumulated = above, accumulated + gain_above

    def price_of(bucket: int) -> float:
        return lowest + (bucket + 0.5) * bucket_width

    levels = [
        ProfileLevel(price=price_of(bucket), label="POC" if bucket == poc_bucket else None, count=count)
        for bucket, count in sorted(counts.items())
    ]
    levels.append(
        ProfileLevel(price=lowest + (included_high + 1) * bucket_width, label="VAH", count=None)
    )
    levels.append(ProfileLevel(price=lowest + included_low * bucket_width, label="VAL", count=None))
    return levels


_TIME_PROFILE = IndicatorSpec(
    id="time_profile",
    name="Time Profile",
    group="profile",
    aliases=("TPO Profile", "Market Profile"),
    inputs=("high", "low", "close"),
    params=(
        Param(name="atr_period", type="int", default=14, min=2, max=5000),
        Param(name="bucket_atr", type="float", default=0.25, min=0.01, max=5.0),
        Param(name="value_area_pct", type="float", default=70.0, min=1.0, max=99.9),
    ),
    render=Render(pane="price", style="histogram"),
    warmup=Warmup(kind="fixed", bars=lambda p: 0),
    computer=TimeProfile(_time_profile_levels),
)


PROFILE: tuple[IndicatorSpec, ...] = (
    _TIME_PROFILE,
)
