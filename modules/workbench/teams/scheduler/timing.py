"""What a cron expression means, in time — one place, because three callers need the same answer. Read as a wall clock
in the schedule's own zone, Poland unless it says otherwise, and returned in UTC: read in UTC it meant the operator wrote
7:00 to start at nine and rewrote it twice a year."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from croniter import croniter

from ..recurrence import DEFAULT_TIMEZONE

SCHEDULE_TIMEZONE = ZoneInfo(DEFAULT_TIMEZONE)


def fires_after(
    cron_expression: str, after: datetime, timezone: ZoneInfo = SCHEDULE_TIMEZONE
) -> Iterator[datetime]:
    """Every moment this expression fires after `after`, in UTC, forever. `croniter` is handed a moment in
    the schedule's timezone and answers in it, which is what makes 9:00 stay 9:00 across a clock change."""
    iterator = croniter(cron_expression, after.astimezone(timezone))
    while True:
        yield iterator.get_next(datetime).astimezone(UTC)


def next_fire_after(
    cron_expression: str, after: datetime | None = None, timezone: ZoneInfo = SCHEDULE_TIMEZONE
) -> datetime:
    """The first moment this expression fires after `after` (by default: now), in UTC."""
    return next(fires_after(cron_expression, after or datetime.now(UTC), timezone))
