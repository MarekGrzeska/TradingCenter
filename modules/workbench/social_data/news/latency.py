"""The delay of one headline — computed from the stored moments on read, so a change of definition never needs
the history rewritten. A source's day is the same definition in SQL (`store.source_figures`)."""

from __future__ import annotations

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
