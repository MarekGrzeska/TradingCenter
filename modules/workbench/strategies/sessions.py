"""The clock of a named session: when it opens and closes in UTC on each local day, from its zone's own rules — so a change
of time moves the session with its city, never by a fixed offset from UTC."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np

from .vocabulary import Session


@dataclass(frozen=True)
class Days:
    """One row per local day around a range: its midnight, and its session's open and close (NaN without one), UTC."""

    midnights: np.ndarray
    opens: np.ndarray
    closes: np.ndarray

    def _day(self, moments: np.ndarray) -> np.ndarray:
        return np.searchsorted(self.midnights, moments, side="right") - 1

    def bar_number(self, starts: np.ndarray, period: int) -> np.ndarray:
        """1 for the first bar starting at or after the open, counted by the clock; 0 for a bar starting outside."""
        day = self._day(starts)
        opens, closes = self.opens[day], self.closes[day]
        with np.errstate(invalid="ignore"):
            inside = (starts >= opens) & (starts < closes)
            number = np.floor((starts - opens) / period) + 1
        return np.where(inside, number, 0.0)

    def minutes_to_close(self, moments: np.ndarray) -> np.ndarray:
        return (self.closes[self._day(moments)] - moments) / 60


def days(session: Session, first: int, last: int) -> Days:
    """Every local day from the one before `first` to the one after `last`, so any moment between has its day. The
    offset is taken once a day: the three zones change time at night, outside every session."""
    zone = ZoneInfo(session.zone)
    start = datetime.fromtimestamp(first, tz=zone).date() - timedelta(days=1)
    count = (datetime.fromtimestamp(last, tz=zone).date() - start).days + 2
    midnights = np.empty(count, dtype=np.int64)
    opens = np.full(count, np.nan)
    closes = np.full(count, np.nan)
    for i in range(count):
        day = start + timedelta(days=i)
        midnights[i] = _utc(day, 0, zone)
        if day.weekday() < 5:
            opens[i] = _utc(day, session.opens, zone)
            closes[i] = _utc(day, session.closes, zone)
    return Days(midnights, opens, closes)


def _utc(day: date, minutes: int, zone: ZoneInfo) -> int:
    return int(datetime.combine(day, time(minutes // 60, minutes % 60), tzinfo=zone).timestamp())
