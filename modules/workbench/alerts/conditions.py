"""A value rule's look: what the tool says, whether that is a yes, and whether a yes is news.

The decision is the part worth reading twice and is pure. A look that could not learn the value is a third thing — not
a no — because a tool that is down for a minute and then answers must not read as the price crossing the level."""

from __future__ import annotations

import json
import operator
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from .catalog import ToolSource

COMPARISONS = {
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
    "eq": operator.eq,
}

# How a comparison reads in a message, in the language the messages are in.
COMPARISON_WORDS = {
    "gt": "powyżej",
    "gte": "co najmniej",
    "lt": "poniżej",
    "lte": "co najwyżej",
    "eq": "równa się",
}


@dataclass(frozen=True)
class Look:
    outcome: Literal["met", "unmet", "unavailable", "refused"]
    value: float | None = None
    reason: str | None = None

    @property
    def result(self) -> bool | None:
        """`True` and `False` are answers; `None` is that no answer was had."""
        if self.outcome == "met":
            return True
        if self.outcome == "unmet":
            return False
        return None


@dataclass(frozen=True)
class Verdict:
    """What a look means for the rule that made it."""

    fire: bool
    # The first look this rule ever managed: it says where the value stands, and nothing about where it has been.
    baseline: bool = False
    # The value crossed the level, and the rule had told too recently to tell again.
    cooled: bool = False


def walk(payload: Any, field_path: str) -> Any:
    """A dotted path into whatever the tool answered; an object by key, a list by index. `None` for any step that does
    not resolve — which the caller reads as 'no number', not as zero."""
    current = payload
    for segment in field_path.split("."):
        if isinstance(current, list):
            try:
                current = current[int(segment)]
            except (ValueError, IndexError):
                return None
        elif isinstance(current, dict):
            current = current.get(segment)
        else:
            return None
    return current


async def look(
    tools: ToolSource | None,
    *,
    tool_name: str,
    arguments: dict[str, Any],
    field_path: str,
    comparison: str,
    threshold: float,
) -> Look:
    if tools is None:
        return Look("unavailable", reason="this process offers no tools to read a value with")
    outcome = await tools.call(tool_name, arguments)
    if outcome.kind == "unavailable":
        return Look("unavailable", reason=f"the tool could not be asked: {outcome.text}")
    if outcome.kind == "refused":
        # Told apart from 'unavailable' on purpose: a tool that said no is not a tool that is down, and the fix differs.
        return Look("refused", reason=f"the tool refused the call: {outcome.text}")
    try:
        payload = json.loads(outcome.text)
    except (json.JSONDecodeError, TypeError):
        return Look("unavailable", reason=f"the answer was not structured data: {outcome.text[:200]!r}")
    value = walk(payload, field_path)
    # A number the answer does not hold is the usual case, not a rare one: a closed market answers with a null price.
    if not isinstance(value, int | float) or isinstance(value, bool):
        return Look("unavailable", reason=f"the answer holds no number at {field_path!r}")
    met = COMPARISONS[comparison](float(value), threshold)
    return Look("met" if met else "unmet", value=float(value))


def decide(
    seen: Look,
    *,
    known: bool | None,
    last_fired_at: datetime | None,
    cooldown_seconds: int,
    now: datetime,
) -> Verdict:
    """Fire on the step from no to yes — not on every look that finds yes. `known` is the last answer actually had, so an
    outage in between neither counts as a no nor hides that the value was already over."""
    result = seen.result
    if result is None:
        return Verdict(fire=False)
    if known is None:
        return Verdict(fire=False, baseline=True)
    if not result or known:
        return Verdict(fire=False)
    cooling = last_fired_at is not None and (now - last_fired_at).total_seconds() < cooldown_seconds
    return Verdict(fire=not cooling, cooled=cooling)
