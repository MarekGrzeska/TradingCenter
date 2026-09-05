"""The strategy of reference against its own twin, decision by decision, where a disagreement is a defect. One
difference is intended: the interpreter computes features in one place, so the twin's refusals carry one more."""

from __future__ import annotations

import pytest

from strategy.catalogue.baseline import moving_average_cross as coded
from strategy.catalogue.baseline_rule import BASELINE_RULE
from strategy.interpreter import spec_from_rule

from .builders import crossing_facts

twin = spec_from_rule(
    strategy_id="baseline_ma_cross_twin",
    name="Baseline · as a written rule",
    description="the same rule, in the node vocabulary",
    rule=BASELINE_RULE,
)

# Every state the coded entry distinguishes. "unsettled and a zero range" is the sharp one: both refusals apply at
# once and it answers "not settled", which is why the twin states settlement as its own first guard.
CASES: dict[str, dict] = {
    "a crossing": {"fast": [1.0, 3.0], "slow": [2.0, 2.0], "atr": [1.0, 1.0]},
    "no crossing": {"fast": [1.0, 1.5], "slow": [2.0, 2.0], "atr": [1.0, 1.0]},
    "already above": {"fast": [3.0, 4.0], "slow": [2.0, 2.0], "atr": [1.0, 1.0]},
    "crossing down": {"fast": [3.0, 1.0], "slow": [2.0, 2.0], "atr": [1.0, 1.0]},
    "touching, not crossing": {"fast": [2.0, 2.0], "slow": [2.0, 2.0], "atr": [1.0, 1.0]},
    "the fast average unsettled": {"fast": [None, 3.0], "slow": [2.0, 2.0], "atr": [1.0, 1.0]},
    "the range unsettled": {"fast": [1.0, 3.0], "slow": [2.0, 2.0], "atr": [1.0, None]},
    "a zero range": {"fast": [1.0, 3.0], "slow": [2.0, 2.0], "atr": [1.0, 0.0]},
    "unsettled and a zero range": {"fast": [None, 3.0], "slow": [2.0, 2.0], "atr": [1.0, 0.0]},
    "a wide crossing": {
        "fast": [1.0, 9.0],
        "slow": [2.0, 2.0],
        "atr": [1.0, 1.0],
        "closes": (100.0, 140.0),
    },
}

PARAMS = coded.resolve_params()


@pytest.mark.parametrize("case", CASES, ids=list(CASES))
def test_the_twin_decides_exactly_what_the_coded_entry_decides(case: str) -> None:
    facts = crossing_facts(**CASES[case])

    theirs = coded.evaluate(facts, PARAMS)
    ours = twin.evaluate(facts, PARAMS)

    assert (ours.action, ours.reason) == (theirs.action, theirs.reason)
    assert (ours.direction, ours.entry, ours.stop, ours.target) == (
        theirs.direction,
        theirs.entry,
        theirs.stop,
        theirs.target,
    )
    assert (ours.rr, ours.score) == (theirs.rr, theirs.score)


@pytest.mark.parametrize("case", CASES, ids=list(CASES))
def test_the_twin_measures_at_least_what_the_coded_entry_measures(case: str) -> None:
    """The one intended difference, asserted as what it is rather than waved past."""
    facts = crossing_facts(**CASES[case])

    theirs = coded.evaluate(facts, PARAMS).features
    ours = twin.evaluate(facts, PARAMS).features

    assert theirs.items() <= ours.items()


def test_the_twin_declares_the_same_facts_and_the_same_parameters() -> None:
    """Not only the same answers: the same reads of the archive and the same ranges, or the
    two would be measured on different data the first time a period was tuned."""
    assert twin.resolve_params() == coded.resolve_params()
    assert [(f.name, f.indicator, f.resolution, dict(f.params)) for f in twin.facts] == [
        (f.name, f.indicator, f.resolution, dict(f.params)) for f in coded.facts
    ]
    assert [(p.name, p.type, p.min, p.max) for p in twin.params] == [
        (p.name, p.type, p.min, p.max) for p in coded.params
    ]


def test_the_twin_is_not_a_second_entry_in_the_catalogue() -> None:
    """A list with two identical baselines on it would make an operator work out which is
    which, and neither answer would be useful."""
    from strategy.catalogue import all_entries

    assert [spec.id for spec in all_entries()] == ["baseline_ma_cross"]
