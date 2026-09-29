"""The delay of one headline and the figures of one source — computed from the stored moments on read, so a
change of definition never needs the history rewritten."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from .models import Delay, Unmeasured

# Two clocks never agree exactly; a feed stamping an item a minute ahead of ours is a clock, not the future.
CLOCK_TOLERANCE = timedelta(seconds=120)


def delay(
    *,
    published_at: datetime | None,
    first_seen_at: datetime,
    previous_fetch_at: datetime | None,
) -> Delay:
    if published_at is None:
        return Delay(None, None, Unmeasured.NO_PUBLISH_TIME)
    if previous_fetch_at is None:
        return Delay(None, None, Unmeasured.FOUND_THERE)
    if published_at > first_seen_at + CLOCK_TOLERANCE:
        return Delay(None, None, Unmeasured.PUBLISH_TIME_IN_FUTURE)
    upper = max(0.0, (first_seen_at - published_at).total_seconds())
    lower = max(0.0, (previous_fetch_at - published_at).total_seconds())
    return Delay(min(lower, upper), upper, None)


def percentile(values: Sequence[float], fraction: float) -> float | None:
    """Linear interpolation between the closest ranks — what PostgreSQL's `percentile_cont` gives."""
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    below = int(position)
    above = min(below + 1, len(ordered) - 1)
    return ordered[below] + (ordered[above] - ordered[below]) * (position - below)


@dataclass(frozen=True, slots=True)
class SourceFigures:
    items: int
    unmeasured: int
    lower_median: float | None
    lower_p90: float | None
    upper_median: float | None
    upper_p90: float | None


def figures(delays: Iterable[Delay]) -> SourceFigures:
    """A source's day. A headline without a delay is counted and kept out of every statistic."""
    measured = list(delays)
    lowers = [d.lower_seconds for d in measured if d.lower_seconds is not None]
    uppers = [d.upper_seconds for d in measured if d.upper_seconds is not None]
    return SourceFigures(
        items=len(measured),
        unmeasured=sum(1 for d in measured if d.unmeasured is not None),
        lower_median=percentile(lowers, 0.5),
        lower_p90=percentile(lowers, 0.9),
        upper_median=percentile(uppers, 0.5),
        upper_p90=percentile(uppers, 0.9),
    )
