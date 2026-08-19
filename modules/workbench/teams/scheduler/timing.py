"""What a cron expression means, in time.

One place, because three callers need the same answer: the route that writes the first
`next_fire_at`, the route that previews the next few, and the clock that rolls the row
forward after a claim (specs/teams-schedules, "Moduł ma jeden zegar").

**The expression is read as a wall clock in Poland, and every moment leaves here in UTC.**
An expression read in UTC meant the operator wrote 7:00 to have the team start at nine,
and rewrote it twice a year; the daily cost ceiling still resets at UTC midnight, so what
moves with the clock change is the gap between that reset and a morning fire — a gap
nobody reads (design.md, "Strefa jako stała modułu").
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from croniter import croniter

SCHEDULE_TIMEZONE = ZoneInfo("Europe/Warsaw")


def fires_after(cron_expression: str, after: datetime) -> Iterator[datetime]:
    """Every moment this expression fires after `after`, in UTC, forever.

    `croniter` is handed a moment in `SCHEDULE_TIMEZONE` and answers in it, which is what
    makes 9:00 stay 9:00 across a clock change. The two nights a year where a wall-clock
    moment does not exist or exists twice are `croniter`'s own call — deterministic, and
    walked by `tests/test_scheduler_clock.py` rather than restated here.
    """
    iterator = croniter(cron_expression, after.astimezone(SCHEDULE_TIMEZONE))
    while True:
        yield iterator.get_next(datetime).astimezone(UTC)


def next_fire_after(cron_expression: str, after: datetime | None = None) -> datetime:
    """The first moment this expression fires after `after` (by default: now), in UTC."""
    return next(fires_after(cron_expression, after or datetime.now(UTC)))
