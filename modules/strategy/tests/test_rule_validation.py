"""The half of a rule's validation that can only be had by asking the archive.

Nothing here repeats what `rule.py` decides on its own. What is under test is the pairing
between a written rule and the catalogue the archive publishes — and every refusal naming
the one thing that has to change, because "invalid definition" sends somebody to read the
whole tree.
"""

from __future__ import annotations

import pytest

from strategy.archive import AnnouncedIndicator, AnnouncedParam
from strategy.errors import DefinitionRefused
from strategy.rule import (
    Compare,
    Const,
    FactRead,
    RuleDefinition,
    RuleFact,
    RuleParam,
    Setup,
)
from strategy.rule_validation import check

# Spelled with floats because that is what the client hands over: `Archive._announced`
# coerces every bound, so a fixture holding ints would be testing a shape nothing produces.
CATALOGUE = {
    "ema": AnnouncedIndicator(
        id="ema",
        name="Exponential moving average",
        group="averages",
        output="lines",
        params=(AnnouncedParam(name="period", type="int", default=20.0, min=2.0, max=5000.0),),
        lines=("ema",),
    ),
    "order_blocks": AnnouncedIndicator(
        id="order_blocks",
        name="Order blocks",
        group="structure",
        output="zones",
        params=(AnnouncedParam(name="lookback", type="int", default=50.0, min=5.0, max=500.0),),
    ),
}


def rule(*, facts=None, params=None, line: str = "ema") -> RuleDefinition:
    return RuleDefinition(
        resolution="HOUR",
        unsettled_reason="not settled",
        no_setup_reason="no setup",
        facts=facts
        or [RuleFact(key="ma", indicator="ema", resolution="HOUR", params={"period": 20})],
        params=params or [],
        setups=[
            Setup(
                when=Compare(op=">", left=FactRead(key="ma", line=line), right=Const(value=0)),
                direction="long",
                entry=Const(value=100.0),
                stop=Const(value=99.0),
                target=Const(value=103.0),
                reason="above",
            )
        ],
    )


def test_a_rule_naming_what_the_archive_announces_passes() -> None:
    check(rule(), CATALOGUE)


def test_an_indicator_the_archive_does_not_announce_is_refused_by_name() -> None:
    with pytest.raises(DefinitionRefused, match="sorcery"):
        check(
            rule(facts=[RuleFact(key="ma", indicator="sorcery", resolution="HOUR")]),
            CATALOGUE,
        )


def test_a_parameter_the_indicator_does_not_take_is_refused_and_the_real_ones_named() -> None:
    with pytest.raises(DefinitionRefused) as refused:
        check(
            rule(
                facts=[
                    RuleFact(
                        key="ma", indicator="ema", resolution="HOUR", params={"lenght": 20}
                    )
                ]
            ),
            CATALOGUE,
        )

    assert "lenght" in str(refused.value)
    assert "period" in str(refused.value)


def test_a_value_outside_the_archives_range_is_refused_with_the_range() -> None:
    with pytest.raises(DefinitionRefused, match=r"\[2.0, 5000.0\]"):
        check(
            rule(
                facts=[
                    RuleFact(
                        key="ma", indicator="ema", resolution="HOUR", params={"period": 90_000}
                    )
                ]
            ),
            CATALOGUE,
        )


def test_a_tunable_ranging_further_than_the_indicator_is_refused_with_both_ranges() -> None:
    """The check whose absence surfaces as a refusal from the archive in the middle of the
    night: everything looks right until somebody tunes the period to the top of the range
    this rule declared, and the archive says no to a value it never accepted."""
    with pytest.raises(DefinitionRefused) as refused:
        check(
            rule(
                facts=[
                    RuleFact(
                        key="ma",
                        indicator="ema",
                        resolution="HOUR",
                        params={"period": "window"},
                    )
                ],
                params=[RuleParam(name="window", type="int", default=20, min=1, max=9_000)],
            ),
            CATALOGUE,
        )

    assert "[1.0, 9000.0]" in str(refused.value)
    assert "[2.0, 5000.0]" in str(refused.value)


def test_a_tunable_inside_the_indicators_range_passes() -> None:
    check(
        rule(
            facts=[
                RuleFact(
                    key="ma", indicator="ema", resolution="HOUR", params={"period": "window"}
                )
            ],
            params=[RuleParam(name="window", type="int", default=20, min=2, max=200)],
        ),
        CATALOGUE,
    )


def test_a_line_the_indicator_does_not_publish_is_refused_and_the_real_ones_named() -> None:
    with pytest.raises(DefinitionRefused) as refused:
        check(rule(line="signal"), CATALOGUE)

    assert "signal" in str(refused.value)
    assert "publishes: ema" in str(refused.value)


def test_reading_a_line_off_an_indicator_that_answers_zones_is_refused() -> None:
    """The vocabulary reads lines and says so. An operator pointing a comparison at a zone
    indicator has misunderstood something, and a rule that ran would answer nothing forever."""
    with pytest.raises(DefinitionRefused, match="zones"):
        check(
            rule(
                facts=[RuleFact(key="ma", indicator="order_blocks", resolution="HOUR")],
            ),
            CATALOGUE,
        )
