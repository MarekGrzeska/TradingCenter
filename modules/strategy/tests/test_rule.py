"""What a rule is refused for before anybody asks the archive anything.

Every refusal here is decidable from the definition alone — a name used and not declared, an
arity that cannot mean anything, a tree past its ceiling. What needs the archive's catalogue
lives in `test_rule_validation.py`, and the split is the same one the two files are written
either side of.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from strategy.rule import (
    MAX_DEPTH,
    MAX_NODES,
    Arith,
    Call,
    Compare,
    Const,
    FactRead,
    Guard,
    Logic,
    ParamRef,
    RuleDefinition,
    RuleFact,
    RuleParam,
    Setup,
)


def rule(**overrides) -> RuleDefinition:
    """The smallest thing this vocabulary calls a rule, with one piece swapped out."""
    base = {
        "resolution": "HOUR",
        "unsettled_reason": "not settled",
        "no_setup_reason": "no setup",
        "facts": [RuleFact(key="ma", indicator="ema", resolution="HOUR", params={"period": 20})],
        "params": [RuleParam(name="mult", type="float", default=2.0, min=0.5, max=6.0)],
        "setups": [
            Setup(
                when=Compare(op=">", left=FactRead(key="ma", line="ema"), right=Const(value=0)),
                direction="long",
                entry=Const(value=100.0),
                stop=Const(value=99.0),
                target=Const(value=103.0),
                reason="above",
            )
        ],
    }
    return RuleDefinition(**{**base, **overrides})


class TestNamesItDeclares:
    def test_a_rule_may_read_what_it_declared(self) -> None:
        assert rule().facts[0].key == "ma"

    def test_a_parameter_read_but_not_declared_is_refused_by_name(self) -> None:
        with pytest.raises(ValidationError, match="wobble"):
            rule(
                setups=[
                    Setup(
                        when=Compare(
                            op=">", left=ParamRef(name="wobble"), right=Const(value=0)
                        ),
                        direction="long",
                        entry=Const(value=100.0),
                        stop=Const(value=99.0),
                        target=Const(value=103.0),
                        reason="above",
                    )
                ]
            )

    def test_a_fact_read_but_not_declared_is_refused_by_name(self) -> None:
        with pytest.raises(ValidationError, match="ghost"):
            rule(
                setups=[
                    Setup(
                        when=Compare(
                            op=">",
                            left=FactRead(key="ghost", line="ema"),
                            right=Const(value=0),
                        ),
                        direction="long",
                        entry=Const(value=100.0),
                        stop=Const(value=99.0),
                        target=Const(value=103.0),
                        reason="above",
                    )
                ]
            )

    def test_a_fact_pointing_at_an_undeclared_parameter_is_refused(self) -> None:
        """A fact parameter naming a tunable is the whole reason a period can be tuned; a
        name that is not there would silently read a different indicator than intended."""
        with pytest.raises(ValidationError, match="nonesuch"):
            rule(
                facts=[
                    RuleFact(
                        key="ma", indicator="ema", resolution="HOUR",
                        params={"period": "nonesuch"},
                    )
                ]
            )

    def test_two_facts_under_one_key_are_refused(self) -> None:
        with pytest.raises(ValidationError, match="fact key"):
            rule(
                facts=[
                    RuleFact(key="ma", indicator="ema", resolution="HOUR"),
                    RuleFact(key="ma", indicator="sma", resolution="HOUR"),
                ]
            )


class TestShapesThatCannotMeanAnything:
    def test_a_default_outside_its_own_range_is_refused(self) -> None:
        """A rule that cannot run with what it ships with, caught where it is written."""
        with pytest.raises(ValidationError, match="outside"):
            RuleParam(name="mult", type="float", default=9.0, min=0.5, max=6.0)

    def test_subtraction_of_three_things_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="exactly two"):
            Arith(op="-", operands=[Const(value=1), Const(value=2), Const(value=3)])

    def test_rounding_to_a_number_that_varies_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="constant"):
            Call(fn="round", operands=[Const(value=1.234), ParamRef(name="mult")])

    def test_a_negation_of_two_things_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="exactly one"):
            Logic(
                op="not",
                operands=[
                    Compare(op=">", left=Const(value=1), right=Const(value=0)),
                    Compare(op="<", left=Const(value=1), right=Const(value=0)),
                ],
            )

    def test_a_key_the_vocabulary_does_not_have_is_refused_rather_than_dropped(self) -> None:
        """The one that matters most: a misspelled key silently ignored would leave a rule
        running and answering a slightly different question than the one that was clicked."""
        with pytest.raises(ValidationError):
            Const.model_validate({"node": "const", "value": 1.0, "valeu": 2.0})

    def test_a_resolution_the_archive_does_not_have_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="MINUTE"):
            rule(resolution="FORTNIGHT")

    def test_a_rule_with_no_setup_is_refused(self) -> None:
        """A rule that can only ever say no is a rule nobody meant to write."""
        with pytest.raises(ValidationError):
            rule(setups=[])

    def test_a_guard_with_an_empty_reason_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            rule(
                guards=[
                    Guard(
                        when=Compare(op=">", left=Const(value=1), right=Const(value=0)),
                        reason="",
                    )
                ]
            )


class TestCeilings:
    def test_a_tree_past_the_node_ceiling_is_refused_with_both_numbers(self) -> None:
        wide = Call(fn="min", operands=[Const(value=float(n)) for n in range(MAX_NODES)])
        with pytest.raises(ValidationError, match=str(MAX_NODES)):
            rule(features={"wide": wide})

    def test_a_tree_past_the_depth_ceiling_is_refused(self) -> None:
        deep = Const(value=1.0)
        for _ in range(MAX_DEPTH + 1):
            deep = Arith(op="+", operands=[deep, Const(value=1.0)])
        with pytest.raises(ValidationError, match="deep"):
            rule(features={"deep": deep})

    def test_more_facts_than_the_ceiling_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            rule(
                facts=[
                    RuleFact(key=f"f{n}", indicator="ema", resolution="HOUR")
                    for n in range(40)
                ]
            )
