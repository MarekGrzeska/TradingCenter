"""Whether an event is one a rule asked for. Pure: the terms the rule was saved with, and the attributes the event came
with. `validation.filter_defects` is the other half — that the terms could ever match — so a term that gets here is one
the schema allowed, and what remains is only whether this event has the value."""

from __future__ import annotations

from typing import Any

from .contract import FilterTerm


def matches(terms: list[FilterTerm], attributes: dict[str, Any]) -> bool:
    """Every term at once. A rule with no terms asks for every event of its type."""
    return all(_holds(term, attributes) for term in terms)


def _holds(term: FilterTerm, attributes: dict[str, Any]) -> bool:
    have = attributes.get(term.attribute)
    if have is None:
        # An attribute the event did not carry is not equal to anything — and is 'not equal' to everything, because
        # 'not this channel' is a thing a film with no channel satisfies.
        return term.op == "ne"
    want = term.value
    try:
        match term.op:
            case "eq":
                return _same(have, want)
            case "ne":
                return not _same(have, want)
            case "in":
                return isinstance(want, list) and any(_same(have, one) for one in want)
            case "contains":
                return isinstance(have, list) and any(_same(one, want) for one in have)
            case "gt":
                return _number(have) > _number(want)
            case "gte":
                return _number(have) >= _number(want)
            case "lt":
                return _number(have) < _number(want)
            case "lte":
                return _number(have) <= _number(want)
    except (TypeError, ValueError):
        # A value that cannot be compared with what the rule says is a value the rule does not want.
        return False
    return False


def _same(have: Any, want: Any) -> bool:
    if isinstance(have, bool) or isinstance(want, bool):
        return have is want
    if isinstance(have, int | float) or isinstance(want, int | float):
        return _number(have) == _number(want)
    return have == want


def _number(value: Any) -> float:
    if isinstance(value, bool):
        raise TypeError("a flag is not a number")
    return float(value)
