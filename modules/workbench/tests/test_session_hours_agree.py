"""The strategy language and the chart name the same three sessions, and neither package may import the other — so the
two are held equal here, by what the chart computes: where its session range starts and ends on a summer and a winter
day, against the language's registry (`strategies-language`, "Te same godziny co na wykresie")."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from market_data.indicators.catalogue import get as indicator
from market_data.indicators.catalogue.spec import Series
from strategies.vocabulary import SESSIONS

CHART = {"NEW_YORK": "session_range_new_york", "LONDON": "session_range_london", "TOKYO": "session_range_tokyo"}


def _local(day: date, minutes: int, zone: str) -> datetime:
    return datetime.combine(day, time(minutes // 60, minutes % 60), tzinfo=ZoneInfo(zone)).astimezone(UTC)


@pytest.mark.parametrize("name", sorted(SESSIONS))
@pytest.mark.parametrize("day", [date(2026, 7, 2), date(2026, 12, 1)])
def test_a_session_of_the_language_is_the_session_the_chart_draws(name: str, day: date) -> None:
    session, spec = SESSIONS[name], indicator(CHART[name])
    midnight = datetime.combine(day, time(), tzinfo=UTC)
    times = [midnight - timedelta(hours=12) + timedelta(minutes=m) for m in range(48 * 60)]
    flat = np.ones(len(times))

    zones = spec.computer.fn(Series(flat, flat, flat, flat), times, spec.resolve_params({}))  # type: ignore[union-attr]

    drawn = {(times[z.start_bar], times[z.end_bar] + timedelta(minutes=1)) for z in zones if z.end_bar is not None}
    assert (_local(day, session.opens, session.zone), _local(day, session.closes, session.zone)) in drawn
