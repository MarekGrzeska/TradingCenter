"""What a cron expression means, in time — one place, because three callers need the same answer.

The expression is read as a wall clock in Poland and every moment leaves here in UTC. Read in UTC it meant
the operator wrote 7:00 to start at nine and rewrote it twice a year; what moves with the clock change is
the gap to the UTC-midnight cost reset, which nobody reads."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from croniter import croniter

SCHEDULE_TIMEZONE = ZoneInfo("Europe/Warsaw")


def fires_after(cron_expression: str, after: datetime) -> Iterator[datetime]:
    """Every moment this expression fires after `after`, in UTC, forever. `croniter` is handed a moment in
    the module's timezone and answers in it, which is what makes 9:00 stay 9:00 across a clock change."""
    iterator = croniter(cron_expression, after.astimezone(SCHEDULE_TIMEZONE))
    while True:
        yield iterator.get_next(datetime).astimezone(UTC)


def next_fire_after(cron_expression: str, after: datetime | None = None) -> datetime:
    """The first moment this expression fires after `after` (by default: now), in UTC."""
    return next(fires_after(cron_expression, after or datetime.now(UTC)))
