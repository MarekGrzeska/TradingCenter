"""What a rule is checked against before it is saved — the half only knowable by asking the archive, never repeating
what `rule.py` decides alone. Refused when written rather than at the first candle, naming the one thing to change."""

from __future__ import annotations

from collections.abc import Mapping

from .archive import AnnouncedIndicator
from .errors import DefinitionRefused
from .rule import FactRead, RuleDefinition, RuleFact, RuleParam


def check(rule: RuleDefinition, catalogue: Mapping[str, AnnouncedIndicator]) -> None:
    """Refuse the rule, or say nothing, reporting the first problem found: a list of eleven complaints, ten of them
    the same missing indicator seen from different angles, is a worse thing to read than one sentence."""
    by_key = {fact.key: fact for fact in rule.facts}
    declared_params = {param.name: param for param in rule.params}

    for fact in rule.facts:
        announced = catalogue.get(fact.indicator)
        if announced is None:
            raise DefinitionRefused(
                f"fact {fact.key!r} names indicator {fact.indicator!r}, which the archive's "
                f"catalogue does not announce"
            )
        _check_fact_parameters(fact, announced, declared_params)

    for node in rule.walk():
        if isinstance(node, FactRead):
            _check_line(node, by_key, catalogue)


def _check_fact_parameters(
    fact: RuleFact,
    announced: AnnouncedIndicator,
    declared_params: Mapping[str, RuleParam],
) -> None:
    for name, value in fact.params.items():
        param = announced.param(name)
        if param is None:
            known = ", ".join(one.name for one in announced.params) or "none"
            raise DefinitionRefused(
                f"fact {fact.key!r} sets {name!r} on {fact.indicator!r}, which takes: {known}"
            )
        if isinstance(value, str):
            _check_range_fits(fact, name, declared_params[value], param)
            continue
        if not param.min <= value <= param.max:
            raise DefinitionRefused(
                f"fact {fact.key!r} sets {name!r} of {fact.indicator!r} to {value}, outside "
                f"the archive's [{param.min}, {param.max}]"
            )


def _check_range_fits(fact: RuleFact, name: str, own, announced) -> None:
    """A tunable pointed at an indicator's parameter may not be tunable further than it. Its absence shows
    up as a refusal from the archive in the middle of the night, on a value it never accepted."""
    if own.min < announced.min or own.max > announced.max:
        raise DefinitionRefused(
            f"parameter {own.name!r} ranges over [{own.min}, {own.max}] and drives {name!r} "
            f"of {fact.indicator!r}, which the archive accepts over "
            f"[{announced.min}, {announced.max}]"
        )


def _check_line(
    node: FactRead,
    by_key: Mapping[str, RuleFact],
    catalogue: Mapping[str, AnnouncedIndicator],
) -> None:
    fact = by_key[node.key]
    announced = catalogue[fact.indicator]
    if announced.output != "lines":
        raise DefinitionRefused(
            f"the rule reads line {node.line!r} of fact {node.key!r}, but {fact.indicator!r} "
            f"answers {announced.output}, not lines — this vocabulary reads lines only"
        )
    if node.line not in announced.lines:
        known = ", ".join(announced.lines) or "none"
        raise DefinitionRefused(
            f"the rule reads line {node.line!r} of fact {node.key!r}; {fact.indicator!r} "
            f"publishes: {known}"
        )
