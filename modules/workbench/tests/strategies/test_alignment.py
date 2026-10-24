"""Another series read under `@`: the last bar available at the decision, never one still forming or not yet published
(`strategies-language`, "Inny interwał i inny instrument", "Wartość jest widoczna od chwili, w której była dostępna")."""

from __future__ import annotations

import numpy as np

from strategies.document import servable, validate
from strategies.evaluate import Evaluator
from strategies.series import Series

from .builders import catalogue
from .market import HOUR, MONDAY, bars, flat, minutes, strategy


def _evaluate(formula: str, extra: dict, tracked: set) -> tuple[np.ndarray, Series]:
    minute = minutes({t: (float(t // 60), float(t // 60), float(t // 60), float(t // 60)) for t in range(0, 2 * 86400, 60)})
    hour = bars(minute, "HOUR")
    checked, problems = validate(
        strategy(entries=[{"side": "long", "when": formula}]), catalogue(), servable(tracked | {("US100", "MINUTE")})
    )
    assert checked is not None, problems
    series = {("US100", "MINUTE"): minute, ("US100", "HOUR"): hour} | extra
    node = checked.formulas["entries[0].when"]
    evaluator = Evaluator(checked, {}, catalogue(), series, {})
    return evaluator.vector(node.operands[0]), hour  # type: ignore[attr-defined]


def test_a_higher_resolution_in_the_middle_of_its_bar_reads_the_one_that_closed() -> None:
    minute = minutes({t: (float(t // 60),) * 4 for t in range(0, 2 * 86400, 60)})
    values, hour = _evaluate("close @ HOUR_4 > 0", {("US100", "HOUR_4"): bars(minute, "HOUR_4")}, set())

    bar = int(np.flatnonzero(hour.available == MONDAY + 10 * HOUR)[0])  # the H1 bar closing at 10:00
    assert values[bar] == (8 * HOUR - 60) // 60  # the H4 bar that closed at 08:00 ended on its 07:59 minute


def test_a_value_published_late_is_not_seen_before_it_was_published() -> None:
    day = Series("DAY", np.array([MONDAY], dtype=np.int64), np.array([MONDAY + 86400 + 14 * HOUR], dtype=np.int64),
                 {k: np.array([42.0]) for k in ("open", "high", "low", "close", "volume")})
    values, hour = _evaluate("close @ US500 @ DAY > 0", {("US500", "DAY"): day}, {("US500", "DAY")})

    at_13 = int(np.flatnonzero(hour.available == MONDAY + 86400 + 13 * HOUR)[0])
    at_15 = int(np.flatnonzero(hour.available == MONDAY + 86400 + 15 * HOUR)[0])
    assert np.isnan(values[at_13]) and values[at_15] == 42.0


def test_a_closed_market_reads_its_last_bar_and_says_it_is_stale() -> None:
    other = bars(minutes(flat(0, 10 * HOUR, 7.0)), "HOUR")  # trades only until 10:00 on Monday
    checked, problems = validate(
        strategy(entries=[{"side": "long", "when": "stale(close @ US500) and close @ US500 == 7"}]), catalogue(),
        servable({("US100", "MINUTE"), ("US500", "MINUTE")}),
    )
    assert checked is not None, problems
    minute = minutes(flat(0, 2 * 86400, 100.0))
    hour = bars(minute, "HOUR")
    evaluator = Evaluator(checked, {}, catalogue(), {("US100", "MINUTE"): minute, ("US100", "HOUR"): hour,
                                                       ("US500", "HOUR"): other}, {})
    condition = evaluator.vector(checked.formulas["entries[0].when"])

    at_9 = int(np.flatnonzero(hour.available == MONDAY + 9 * HOUR)[0])
    at_20 = int(np.flatnonzero(hour.available == MONDAY + 20 * HOUR)[0])
    assert not condition[at_9] and condition[at_20]


def test_two_reads_of_a_series_that_changed_have_different_fingerprints() -> None:
    first = bars(minutes(flat(0, 2 * HOUR, 100.0)), "HOUR")
    second = bars(minutes(flat(0, HOUR, 100.0) | flat(HOUR, 2 * HOUR, 101.0)), "HOUR")

    assert first.fingerprint()["sha256"] != second.fingerprint()["sha256"]
    assert first.fingerprint() == bars(minutes(flat(0, 2 * HOUR, 100.0)), "HOUR").fingerprint()
