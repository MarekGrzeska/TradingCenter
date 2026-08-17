"""The rhythm a schedule is described by, and its translation to the cron expression the
clock actually runs (specs/teams-schedules, "Harmonogram da się opisać rytmem, a moduł zna
oba zapisy").

The translation lives here, in the module, and exactly once: a caller that had to repeat
it to show an operator their own schedule would eventually show something other than what
the clock does (specs/terminal-teams-schedules, "Terminal nie liczy czasu wyzwolenia sam").

`from_cron` is deliberately narrow — it answers with a rhythm only for an expression that
is *exactly* what `to_cron` would produce for it, and with `None` for everything else.
That is what keeps the pair honest: an operator who wrote their own expression under
"Advanced" gets it back unchanged rather than rounded into the nearest rhythm.

Weekdays are ISO here — 1 is Monday, 7 is Sunday — because that is the week an operator
reads. Cron's own numbering (0 is Sunday) only exists inside `to_cron`/`from_cron`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

RecurrenceKind = Literal["every_minutes", "hourly", "daily", "weekly", "monthly"]

# Which fields each rhythm needs. Everything not named here MUST be absent, which is what
# stops a `daily` carrying weekdays nobody will ever look at.
_FIELDS: dict[RecurrenceKind, frozenset[str]] = {
    "every_minutes": frozenset({"minutes"}),
    "hourly": frozenset({"minute"}),
    "daily": frozenset({"hour", "minute"}),
    "weekly": frozenset({"hour", "minute", "weekdays"}),
    "monthly": frozenset({"hour", "minute", "day_of_month"}),
}

_OPTIONAL = frozenset({"minutes", "minute", "hour", "weekdays", "day_of_month"})


class Recurrence(BaseModel):
    """One rhythm, in the operator's own words. `kind` decides which of the other fields
    carry a value — see `_FIELDS`."""

    kind: RecurrenceKind
    # `every_minutes` only. Cron's step form does not cross the hour, so neither does this:
    # anything longer is a rhythm with an hour in it, or an expression under "Advanced".
    minutes: int | None = Field(default=None, ge=1, le=59)
    minute: int | None = Field(default=None, ge=0, le=59)
    hour: int | None = Field(default=None, ge=0, le=23)
    # ISO weekdays: 1 Monday … 7 Sunday.
    weekdays: list[int] | None = None
    day_of_month: int | None = Field(default=None, ge=1, le=31)

    @model_validator(mode="after")
    def _fields_match_kind(self) -> Recurrence:
        needed = _FIELDS[self.kind]
        for name in _OPTIONAL:
            value = getattr(self, name)
            if name in needed and value is None:
                raise ValueError(f"recurrence kind {self.kind!r} needs {name}")
            if name not in needed and value is not None:
                raise ValueError(f"recurrence kind {self.kind!r} must not carry {name}")
        if self.weekdays is not None:
            if not self.weekdays:
                raise ValueError("weekdays must name at least one day")
            if any(day < 1 or day > 7 for day in self.weekdays):
                raise ValueError("weekdays are 1 (Monday) through 7 (Sunday)")
            if len(set(self.weekdays)) != len(self.weekdays):
                raise ValueError("weekdays must not repeat")
        return self


def _cron_weekday(iso_day: int) -> int:
    """ISO Sunday (7) is cron Sunday (0). Both numberings accept 7 for Sunday, but only
    one of them is what `from_cron` will read back, so the canonical form uses 0."""
    return 0 if iso_day == 7 else iso_day


def _iso_weekday(cron_day: int) -> int:
    return 7 if cron_day == 0 else cron_day


def to_cron(recurrence: Recurrence) -> str:
    """The five-field expression this rhythm means. Total: `Recurrence`'s own validator
    has already refused every shape this could not express."""
    if recurrence.kind == "every_minutes":
        return f"*/{recurrence.minutes} * * * *"
    if recurrence.kind == "hourly":
        return f"{recurrence.minute} * * * *"
    if recurrence.kind == "daily":
        return f"{recurrence.minute} {recurrence.hour} * * *"
    if recurrence.kind == "weekly":
        assert recurrence.weekdays is not None
        days = ",".join(str(day) for day in sorted(_cron_weekday(d) for d in recurrence.weekdays))
        return f"{recurrence.minute} {recurrence.hour} * * {days}"
    return f"{recurrence.minute} {recurrence.hour} {recurrence.day_of_month} * *"


def from_cron(expression: str) -> Recurrence | None:
    """The rhythm this expression is, or `None` when it is not one of them.

    Every candidate is checked by generating it back: a rhythm is returned only when
    `to_cron` of it is this expression again. That is one line of proof instead of five
    parsers each having to be as strict as the writer that produced them.
    """
    fields = expression.split()
    if len(fields) != 5:
        return None
    minute, hour, day_of_month, month, weekday = fields
    if month != "*":
        return None

    candidate = _candidate(minute, hour, day_of_month, weekday)
    if candidate is None:
        return None
    return candidate if to_cron(candidate) == expression else None


def _candidate(minute: str, hour: str, day_of_month: str, weekday: str) -> Recurrence | None:
    try:
        if minute.startswith("*/") and (hour, day_of_month, weekday) == ("*", "*", "*"):
            return Recurrence(kind="every_minutes", minutes=int(minute[2:]))
        if (hour, day_of_month, weekday) == ("*", "*", "*"):
            return Recurrence(kind="hourly", minute=int(minute))
        if (day_of_month, weekday) == ("*", "*"):
            return Recurrence(kind="daily", minute=int(minute), hour=int(hour))
        if day_of_month == "*" and weekday != "*":
            return Recurrence(
                kind="weekly",
                minute=int(minute),
                hour=int(hour),
                weekdays=sorted(_iso_weekday(int(day)) for day in weekday.split(",")),
            )
        if weekday == "*":
            return Recurrence(
                kind="monthly",
                minute=int(minute),
                hour=int(hour),
                day_of_month=int(day_of_month),
            )
    except ValueError:
        # A field that is not a plain number (a range, a list, a step outside the minute
        # field) is simply not one of these rhythms — the same answer as a shape nobody
        # here recognises.
        return None
    return None
