"""How a written rule evaluates — the three-valued part above all.

The property under test throughout is the one the whole platform stands on: a reading the
archive did not compute is neither a number nor a zero, and a question that cannot be
answered refuses rather than passes. Everything else here is arithmetic.
"""

from __future__ import annotations

import pytest
from builders import facts as build_facts
from builders import line

from strategy.interpreter import interpret, spec_from_rule
from strategy.rule import (
    Arith,
    BarRead,
    Call,
    Compare,
    Const,
    Crossed,
    FactRead,
    Guard,
    Logic,
    ParamRef,
    Previous,
    RuleDefinition,
    RuleFact,
    RuleParam,
    Settled,
    Setup,
)
from strategy.spec import FactValue

UNSETTLED = "the reading has not settled"
NO_SETUP = "nothing to take here"


def rule(*, when=None, guards=(), features=None, entry=None, stop=None, target=None, score=None):
    return RuleDefinition(
        resolution="HOUR",
        unsettled_reason=UNSETTLED,
        no_setup_reason=NO_SETUP,
        facts=[RuleFact(key="ma", indicator="ema", resolution="HOUR", params={"period": 20})],
        params=[RuleParam(name="mult", type="float", default=2.0, min=0.5, max=6.0)],
        guards=list(guards),
        setups=[
            Setup(
                when=when
                or Compare(op=">", left=FactRead(key="ma", line="ema"), right=Const(value=0)),
                direction="long",
                entry=entry or BarRead(field="close"),
                stop=stop or Const(value=99.0),
                target=target or Const(value=103.0),
                score=score,
                reason="it held",
            )
        ],
        features=features or {},
    )


def facts(values=(1.0, 2.0), *, closes=(100.0, 101.0), key="ma", name="ema", error=None):
    reading = line(key, name, list(values))
    if error is not None:
        reading = FactValue(key=key, resolution="HOUR", error=error)
    return build_facts(closes=closes, values={key: reading})


def decide(one: RuleDefinition, given, params=None):
    return interpret(one, given, params or {"mult": 2.0})


class TestWhatTheArchiveCouldNotAnswer:
    def test_a_declared_fact_that_was_not_read_refuses(self) -> None:
        answer = decide(rule(), build_facts(values={}))

        assert answer.action == "no_trade"
        assert "declared was not read" in (answer.reason or "")

    def test_a_fact_the_archive_could_not_compute_refuses_by_name(self) -> None:
        """Never read as "there was nothing": a strategy that cannot see is not one that
        saw nothing, and the record has to say which it was."""
        answer = decide(rule(), facts(error="no series at this resolution"))

        assert answer.action == "no_trade"
        assert "ma" in (answer.reason or "")
        assert "no series at this resolution" in (answer.reason or "")

    def test_a_line_that_has_not_filled_yet_refuses_with_the_declared_reason(self) -> None:
        answer = decide(rule(), facts(values=(None, None)))

        assert answer.action == "no_trade"
        assert answer.reason == UNSETTLED

    def test_reaching_before_the_series_began_is_not_a_number(self) -> None:
        """Offset past the start is warmup, not a zero — the difference between refusing a
        bar and inventing a crossing that never happened."""
        answer = decide(
            rule(
                when=Compare(
                    op=">", left=FactRead(key="ma", line="ema", offset=9), right=Const(value=0)
                )
            ),
            facts(values=(1.0, 2.0)),
        )

        assert answer.reason == UNSETTLED


class TestThreeValuedLogic:
    def test_a_conjunction_with_an_outright_false_is_false(self) -> None:
        """Settled by the false whatever else is missing — Kleene's rule, and the one that
        does not throw information away."""
        answer = decide(
            rule(
                when=Logic(
                    op="all",
                    operands=[
                        Compare(op=">", left=Const(value=1), right=Const(value=5)),
                        Compare(
                            op=">", left=FactRead(key="ma", line="ema"), right=Const(value=0)
                        ),
                    ],
                )
            ),
            facts(values=(None, None)),
        )

        assert answer.reason == NO_SETUP

    def test_a_conjunction_of_true_and_undetermined_refuses(self) -> None:
        answer = decide(
            rule(
                when=Logic(
                    op="all",
                    operands=[
                        Compare(op="<", left=Const(value=1), right=Const(value=5)),
                        Compare(
                            op=">", left=FactRead(key="ma", line="ema"), right=Const(value=0)
                        ),
                    ],
                )
            ),
            facts(values=(None, None)),
        )

        assert answer.reason == UNSETTLED

    def test_a_disjunction_with_an_outright_true_is_true(self) -> None:
        answer = decide(
            rule(
                when=Logic(
                    op="any",
                    operands=[
                        Compare(op="<", left=Const(value=1), right=Const(value=5)),
                        Compare(
                            op=">", left=FactRead(key="ma", line="ema"), right=Const(value=0)
                        ),
                    ],
                )
            ),
            facts(values=(None, None)),
        )

        assert answer.action == "trade"

    def test_settled_answers_rather_than_propagating(self) -> None:
        """The one node that is never undetermined — which is what lets a rule state
        "refuse unless these have been computed" as its first guard."""
        answer = decide(
            rule(
                guards=[
                    Guard(
                        when=Logic(
                            op="not", operands=[Settled(of=[FactRead(key="ma", line="ema")])]
                        ),
                        reason="the reading is not there yet",
                    )
                ]
            ),
            facts(values=(None, None)),
        )

        assert answer.reason == "the reading is not there yet"


class TestTotality:
    def test_dividing_by_a_range_that_came_out_zero_refuses_rather_than_raising(self) -> None:
        """A rule that raised would take the loop's whole pass with it, and "this could not
        be worked out" is already a decision this platform records."""
        answer = decide(
            rule(
                when=Compare(
                    op=">",
                    left=Arith(op="/", operands=[Const(value=1.0), FactRead(key="ma", line="ema")]),
                    right=Const(value=0),
                )
            ),
            facts(values=(1.0, 0.0)),
        )

        assert answer.reason == UNSETTLED

    def test_a_stop_that_works_out_to_the_entry_refuses_with_a_reason(self) -> None:
        """Not knowable when the rule was saved: both numbers come out of arithmetic on
        readings, so this stays a refusal at the bar."""
        answer = decide(rule(stop=BarRead(field="close")), facts())

        assert answer.action == "no_trade"
        assert "no risk to size against" in (answer.reason or "")


class TestArithmetic:
    def test_a_crossing_reads_this_bar_and_the_one_before(self) -> None:
        crossing = rule(
            when=Crossed(
                direction="above",
                left=FactRead(key="ma", line="ema"),
                right=Const(value=5.0),
            )
        )

        assert decide(crossing, facts(values=(4.0, 6.0))).action == "trade"
        # Already above on both bars: nothing crossed on this one.
        assert decide(crossing, facts(values=(6.0, 7.0))).action == "no_trade"

    def test_previous_shifts_the_whole_expression_by_one_bar(self) -> None:
        answer = decide(
            rule(
                when=Compare(
                    op=">",
                    left=Previous(of=FactRead(key="ma", line="ema")),
                    right=Const(value=5.0),
                )
            ),
            facts(values=(9.0, 1.0)),
        )

        assert answer.action == "trade"

    def test_levels_and_score_are_arithmetic_over_readings_and_parameters(self) -> None:
        answer = decide(
            rule(
                stop=Arith(
                    op="-",
                    operands=[
                        BarRead(field="close"),
                        Arith(
                            op="*",
                            operands=[ParamRef(name="mult"), FactRead(key="ma", line="ema")],
                        ),
                    ],
                ),
                target=Const(value=110.0),
                score=Call(fn="round", operands=[Const(value=1.23456), Const(value=2)]),
            ),
            facts(values=(1.0, 3.0)),
        )

        assert answer.stop == pytest.approx(101.0 - 2.0 * 3.0)
        assert answer.score == 1.23

    def test_a_feature_that_could_not_be_worked_out_is_dropped_not_refused(self) -> None:
        """Features are what a report attributes an edge to, never what a decision rests
        on — so one that came out undetermined costs the decision nothing."""
        answer = decide(
            rule(
                features={
                    "here": Const(value=1.0),
                    "gone": FactRead(key="ma", line="nosuchline"),
                }
            ),
            facts(values=(1.0, 2.0)),
        )

        assert answer.features == {"here": 1.0}


class TestDeterminism:
    def test_the_same_tree_and_the_same_readings_give_the_same_decision(self) -> None:
        """On this stands the unit test on facts by hand, the replay of a recorded decision
        and the backtest calling the very same function."""
        one = rule(
            score=Call(fn="min", operands=[FactRead(key="ma", line="ema"), Const(value=9.0)]),
            features={"reading": FactRead(key="ma", line="ema")},
        )
        given = facts(values=(1.0, 2.5))

        first = interpret(one, given, {"mult": 2.0})
        second = interpret(one, given, {"mult": 2.0})

        assert first == second


class TestAsACatalogueEntry:
    def test_a_revision_becomes_an_ordinary_spec(self) -> None:
        """What makes a clicked strategy indistinguishable downstream: the loop, the gates
        and the backtest are handed a `StrategySpec` and never learn where it came from."""
        spec = spec_from_rule(
            strategy_id="written", name="Written", description="d", rule=rule()
        )

        assert spec.id == "written"
        assert spec.indicators == ("ema",)
        assert spec.resolve_params() == {"mult": 2.0}
        assert spec.evaluate(facts(values=(1.0, 2.0)), {"mult": 2.0}).action == "trade"
