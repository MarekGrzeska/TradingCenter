"""The rhythm a schedule is described by, and its translation to the cron expression the clock runs. The
translation lives here exactly once: a caller that repeated it would eventually show something else.

`from_cron` is deliberately narrow — a rhythm only for an expression that is exactly what `to_cron` would
produce, so an operator who wrote their own gets it back unrounded. Weekdays are ISO here, because that is
the week an operator reads, and they ride on three rhythms rather than one."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

RecurrenceKind = Literal["every_minutes", "hourly", "daily", "weekly", "monthly"]

# Which fields each rhythm needs. A field named here MUST carry a value.
_REQUIRED: dict[RecurrenceKind, frozenset[str]] = {
    "every_minutes": frozenset({"minutes"}),
    "hourly": frozenset({"minute"}),
    "daily": frozenset({"hour", "minute"}),
    "weekly": frozenset({"hour", "minute", "weekdays"}),
    "monthly": frozenset({"hour", "minute", "day_of_month"}),
}

# Which fields a rhythm MAY carry. Weekdays on the two that repeat more often than once a day, because the
# market is shut two days in seven. `daily` is absent: daily plus weekdays is exactly `weekly`'s expression.
_ALLOWED: dict[RecurrenceKind, frozenset[str]] = {
    "every_minutes": frozenset({"weekdays"}),
    "hourly": frozenset({"weekdays"}),
}

_OPTIONAL = frozenset({"minutes", "minute", "hour", "weekdays", "day_of_month"})

_EVERY_DAY = frozenset(range(1, 8))


class Recurrence(BaseModel):
    """One rhythm, in the operator's own words. `kind` decides which of the other fields carry a value, and
    anything else is refused rather than ignored. Weekdays are ISO, and their absence means every day."""

    kind: RecurrenceKind
    # `every_minutes` only. Cron's step form does not cross the hour, so neither does this:
    # anything longer is a rhythm with an hour in it, or an expression under "Advanced".
    minutes: int | None = Field(default=None, ge=1, le=59)
    minute: int | None = Field(default=None, ge=0, le=59)
    hour: int | None = Field(default=None, ge=0, le=23)
    # ISO weekdays: 1 Monday … 7 Sunday. Required by `weekly`, optional on the two that repeat within a
    # day. `None` means every day, and every day named normalises back to `None`.
    weekdays: list[int] | None = None
    day_of_month: int | None = Field(default=None, ge=1, le=31)

    @model_validator(mode="after")
    def _fields_match_kind(self) -> Recurrence:
        needed = _REQUIRED[self.kind]
        may_carry = needed | _ALLOWED.get(self.kind, frozenset())
        for name in _OPTIONAL:
            value = getattr(self, name)
            if name in needed and value is None:
                raise ValueError(f"recurrence kind {self.kind!r} needs {name}")
            if name not in may_carry and value is not None:
                if name == "weekdays":
                    # Named rather than merely refused: the rhythm this operator wants
                    # exists, it is just the other one.
                    raise ValueError(
                        f"recurrence kind {self.kind!r} must not carry weekdays — a rhythm "
                        "of one moment a day on chosen weekdays is kind 'weekly'"
                    )
                raise ValueError(f"recurrence kind {self.kind!r} must not carry {name}")
        if self.weekdays is not None:
            if not self.weekdays:
                raise ValueError("weekdays must name at least one day")
            if any(day < 1 or day > 7 for day in self.weekdays):
                raise ValueError("weekdays are 1 (Monday) through 7 (Sunday)")
            if len(set(self.weekdays)) != len(self.weekdays):
                raise ValueError("weekdays must not repeat")
            # Every day named is the same trigger as no day named, and a rhythm handed back in another
            # shape is one the operator did not set. Not for `weekly`, whose seven days are their own.
            if self.kind != "weekly" and set(self.weekdays) == _EVERY_DAY:
                self.weekdays = None
        return self


def _cron_weekday(iso_day: int) -> int:
    """ISO Sunday (7) is cron Sunday (0). Both numberings accept 7 for Sunday, but only
    one of them is what `from_cron` will read back, so the canonical form uses 0."""
    return 0 if iso_day == 7 else iso_day


def _iso_weekday(cron_day: int) -> int:
    return 7 if cron_day == 0 else cron_day


def _cron_days(weekdays: list[int] | None) -> str:
    """The fifth field for these days — `*` for "no day named", which is every day. A list rather than a
    range, because one canonical spelling per trigger is what lets `from_cron` answer with one rhythm."""
    if weekdays is None:
        return "*"
    return ",".join(str(day) for day in sorted(_cron_weekday(d) for d in weekdays))


def to_cron(recurrence: Recurrence) -> str:
    """The five-field expression this rhythm means. Total: `Recurrence`'s own validator
    has already refused every shape this could not express."""
    if recurrence.kind == "every_minutes":
        return f"*/{recurrence.minutes} * * * {_cron_days(recurrence.weekdays)}"
    if recurrence.kind == "hourly":
        return f"{recurrence.minute} * * * {_cron_days(recurrence.weekdays)}"
    if recurrence.kind == "daily":
        return f"{recurrence.minute} {recurrence.hour} * * *"
    if recurrence.kind == "weekly":
        assert recurrence.weekdays is not None
        return f"{recurrence.minute} {recurrence.hour} * * {_cron_days(recurrence.weekdays)}"
    return f"{recurrence.minute} {recurrence.hour} {recurrence.day_of_month} * *"


def from_cron(expression: str) -> Recurrence | None:
    """The rhythm this expression is, or `None` when it is not one of them. Every candidate is checked by
    generating it back — one line of proof instead of five parsers each as strict as the writer."""
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


def _iso_days(weekday: str) -> list[int]:
    return sorted(_iso_weekday(int(day)) for day in weekday.split(","))


def _candidate(minute: str, hour: str, day_of_month: str, weekday: str) -> Recurrence | None:
    try:
        # The two rhythms that repeat within a day read the same whether the fifth field names days or
        # not. They come before the `weekly` branch, which would otherwise take a `*` hour to `int()`.
        if minute.startswith("*/") and (hour, day_of_month) == ("*", "*"):
            days = None if weekday == "*" else _iso_days(weekday)
            return Recurrence(kind="every_minutes", minutes=int(minute[2:]), weekdays=days)
        if (hour, day_of_month) == ("*", "*"):
            days = None if weekday == "*" else _iso_days(weekday)
            return Recurrence(kind="hourly", minute=int(minute), weekdays=days)
        if (day_of_month, weekday) == ("*", "*"):
            return Recurrence(kind="daily", minute=int(minute), hour=int(hour))
        if day_of_month == "*" and weekday != "*":
            return Recurrence(
                kind="weekly",
                minute=int(minute),
                hour=int(hour),
                weekdays=_iso_days(weekday),
            )
        if weekday == "*":
            return Recurrence(
                kind="monthly",
                minute=int(minute),
                hour=int(hour),
                day_of_month=int(day_of_month),
            )
    except ValueError:
        # A field that is not a plain number is simply not one of these rhythms — the same answer as a
        # shape nobody here recognises.
        return None
    return None
