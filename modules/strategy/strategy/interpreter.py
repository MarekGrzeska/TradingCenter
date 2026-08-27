"""Evaluating a rule, which is the `evaluate` of every clicked-together strategy: a catalogue entry's equal, reaching
nothing outside its arguments. Three-valued, closed on refusal, and total — a rule that raised would take the pass."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import partial

from .rule import (
    Arith,
    BarRead,
    Call,
    Compare,
    Const,
    Crossed,
    FactRead,
    Logic,
    Numeric,
    ParamRef,
    Previous,
    RuleDefinition,
    Settled,
)
from .spec import Decision, Fact, Facts, Param, StrategySpec

# The two refusals the platform states for every rule, because they are about the reading rather than the
# strategy. Worded as the hand-written entry of reference words them, so twins answer the same sentence.
FACT_NOT_READ = "a fact this strategy declared was not read"
STOP_IS_ENTRY = "the stop worked out to the entry, so there is no risk to size against"


@dataclass(frozen=True)
class _Env:
    """What one node may know. `shift` is how many bars back the frame currently sits."""

    facts: Facts
    params: Mapping[str, float]
    shift: int = 0

    def back(self, bars: int) -> _Env:
        return _Env(facts=self.facts, params=self.params, shift=self.shift + bars)


def interpret(rule: RuleDefinition, facts: Facts, params: Mapping[str, float]) -> Decision:
    """One rule, one bar, one decision. The order is the whole of what a rule means: every declared
    fact present, none of them an error, the guards in order, the features, then the setups in order."""
    env = _Env(facts=facts, params=params)

    for declared in rule.facts:
        if facts.get(declared.key) is None:
            return Decision.no_trade(FACT_NOT_READ)
    for declared in rule.facts:
        value = facts.values[declared.key]
        if value.error is not None:
            # The archive saying it could not compute this one — never that the answer was
            # nothing. Refusing here keeps a missing reading from reading as a signal.
            return Decision.no_trade(f"the archive could not compute {value.key}: {value.error}")

    for guard in rule.guards:
        answer = _truth(guard.when, env)
        if answer is None:
            return Decision.no_trade(rule.unsettled_reason)
        if answer:
            return Decision.no_trade(guard.reason)

    # A feature that could not be worked out is dropped rather than turned into a refusal:
    # features are what a report attributes an edge to, not what a decision rests on.
    features = {
        name: value
        for name, value in ((name, _number(node, env)) for name, node in rule.features.items())
        if value is not None
    }

    for setup in rule.setups:
        answer = _truth(setup.when, env)
        if answer is None:
            return Decision.no_trade(rule.unsettled_reason, features=features)
        if not answer:
            continue
        entry = _number(setup.entry, env)
        stop = _number(setup.stop, env)
        target = _number(setup.target, env)
        score = None if setup.score is None else _number(setup.score, env)
        if entry is None or stop is None or target is None:
            # The condition held but a level did not work out. Undetermined levels are the
            # same state as an undetermined question, so they carry the same sentence.
            return Decision.no_trade(rule.unsettled_reason, features=features)
        try:
            return Decision.trade(
                direction=setup.direction,
                entry=entry,
                stop=stop,
                target=target,
                score=score,
                features=features,
                reason=setup.reason,
            )
        except ValueError:
            # `Decision` refuses a trade whose stop is its entry, and it is right to: there is nothing
            # to size against. Not knowable when the rule was saved, since both come out of arithmetic.
            return Decision.no_trade(STOP_IS_ENTRY, features=features)

    return Decision.no_trade(rule.no_setup_reason, features=features)


def spec_from_rule(
    *, strategy_id: str, name: str, description: str, rule: RuleDefinition
) -> StrategySpec:
    """One revision as an ordinary catalogue entry. This is what makes a clicked strategy
    indistinguishable downstream: everything below is handed a `StrategySpec` and never learns its origin."""
    return StrategySpec(
        id=strategy_id,
        name=name,
        description=description,
        resolution=rule.resolution,
        evaluate=partial(interpret, rule),
        facts=tuple(
            Fact(
                indicator=fact.indicator,
                resolution=fact.resolution,
                params=dict(fact.params),
                key=fact.key,
                bars=fact.bars,
            )
            for fact in rule.facts
        ),
        params=tuple(
            Param(
                name=param.name,
                type=param.type,
                default=param.default,
                min=param.min,
                max=param.max,
            )
            for param in rule.params
        ),
        candles=rule.candles,
    )



def _number(node: Numeric, env: _Env) -> float | None:
    if isinstance(node, Const):
        return node.value
    if isinstance(node, ParamRef):
        # `.get` rather than indexing: validation has already established the name, and a
        # total function is worth more here than an exception that would be a bug either way.
        value = env.params.get(node.name)
        return None if value is None else float(value)
    if isinstance(node, FactRead):
        return _from_fact(node, env)
    if isinstance(node, BarRead):
        return _from_bar(node, env)
    if isinstance(node, Previous):
        return _number(node.of, env.back(1))
    if isinstance(node, Arith):
        return _arith(node, env)
    if isinstance(node, Call):
        return _call(node, env)
    raise AssertionError(f"unreachable node {node!r}")  # pragma: no cover


def _from_fact(node: FactRead, env: _Env) -> float | None:
    value = env.facts.get(node.key)
    if value is None or value.error is not None:
        return None
    series = value.line(node.line)
    index = len(series) - 1 - (node.offset + env.shift)
    if index < 0:
        # Reaching before the series began. Not an error and not a zero: the archive read
        # less history than this reading needs, which is exactly "not settled".
        return None
    return series[index]


def _from_bar(node: BarRead, env: _Env) -> float | None:
    candles = env.facts.candles
    index = len(candles) - 1 - (node.offset + env.shift)
    if index < 0:
        return None
    return float(getattr(candles[index], node.field))


def _arith(node: Arith, env: _Env) -> float | None:
    values = [_number(operand, env) for operand in node.operands]
    if any(value is None for value in values):
        return None
    numbers = [value for value in values if value is not None]
    if node.op == "+":
        total = numbers[0]
        for value in numbers[1:]:
            total += value
        return total
    if node.op == "*":
        product = numbers[0]
        for value in numbers[1:]:
            product *= value
        return product
    if node.op == "-":
        return numbers[0] - numbers[1]
    if numbers[1] == 0:
        # Undetermined rather than an exception, and undetermined rather than infinity: a
        # rule dividing by a range that came out zero has nothing to say about this bar.
        return None
    return numbers[0] / numbers[1]


def _call(node: Call, env: _Env) -> float | None:
    values = [_number(operand, env) for operand in node.operands]
    if any(value is None for value in values):
        return None
    numbers = [value for value in values if value is not None]
    if node.fn == "abs":
        return abs(numbers[0])
    if node.fn == "min":
        return min(numbers)
    if node.fn == "max":
        return max(numbers)
    return round(numbers[0], int(numbers[1]))



def _truth(node: object, env: _Env) -> bool | None:
    if isinstance(node, Compare):
        left = _number(node.left, env)
        right = _number(node.right, env)
        if left is None or right is None:
            return None
        if node.op == "<":
            return left < right
        if node.op == "<=":
            return left <= right
        if node.op == ">":
            return left > right
        return left >= right
    if isinstance(node, Crossed):
        return _crossed(node, env)
    if isinstance(node, Settled):
        # The one question that is never undetermined — that is its whole purpose.
        return all(_number(operand, env) is not None for operand in node.of)
    if isinstance(node, Logic):
        return _logic(node, env)
    raise AssertionError(f"unreachable node {node!r}")  # pragma: no cover


def _logic(node: Logic, env: _Env) -> bool | None:
    answers = [_truth(operand, env) for operand in node.operands]
    if node.op == "not":
        return None if answers[0] is None else not answers[0]
    if node.op == "all":
        # An outright false settles it whatever else is missing; only a missing operand
        # among otherwise-true ones leaves the conjunction undetermined.
        if any(answer is False for answer in answers):
            return False
        return None if any(answer is None for answer in answers) else True
    if any(answer is True for answer in answers):
        return True
    return None if any(answer is None for answer in answers) else False


def _crossed(node: Crossed, env: _Env) -> bool | None:
    """Both sides, on this bar and the one before, from the same two expressions — one expression in two
    frames rather than two declarations that must agree."""
    before = env.back(1)
    now_left = _number(node.left, env)
    now_right = _number(node.right, env)
    was_left = _number(node.left, before)
    was_right = _number(node.right, before)
    if None in (now_left, now_right, was_left, was_right):
        return None
    assert now_left is not None and now_right is not None
    assert was_left is not None and was_right is not None
    if node.direction == "above":
        return was_left <= was_right and now_left > now_right
    return was_left >= was_right and now_left < now_right
