"""What a rule is checked against before it is ever saved.

**Everything here needs an answer from the archive.** What `rule.py` can decide alone — the
shape of the tree, arities, names it declares and then uses, the ceilings — it decides
alone, and this file never repeats it. What is left is the half that is only knowable by
asking: whether an indicator exists, what it is called, what it answers, which lines it
publishes and what range each of its parameters accepts.

**Refused at the moment it is written, the way a team definition is.** A rule that cannot
run is something the operator can still see on the screen they wrote it on; an hour later it
is a strategy that quietly records nothing. Every refusal below names the one thing that has
to change, because "invalid definition" sends somebody to read the whole tree.

**This does not replace the check at registration.** The archive's catalogue can change
between writing a rule and starting a watch on it, so `catalogue.check_facts_are_announced`
stays exactly where it is. This is the earlier, friendlier half of the same question, not a
substitute for the one that actually guards the loop (design.md, decision 8).
"""

from __future__ import annotations

from collections.abc import Mapping

from .archive import AnnouncedIndicator
from .errors import DefinitionRefused
from .rule import FactRead, RuleDefinition, RuleFact, RuleParam


def check(rule: RuleDefinition, catalogue: Mapping[str, AnnouncedIndicator]) -> None:
    """Refuse the rule, or say nothing. The first problem found is the one reported.

    First rather than all: a list of eleven complaints, ten of which are the same missing
    indicator seen from different angles, is a worse thing to read than one sentence.
    """
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
    """A tunable pointed at an indicator's parameter may not be tunable further than it.

    The check whose absence shows up as a refusal from the archive in the middle of the
    night: everything looks right until the day somebody tunes the period to the top of the
    range this rule declared and the archive says no to a value it never accepted
    (`strategy-configurator`, "Definicja jest odrzucana w chwili zapisu").
    """
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
