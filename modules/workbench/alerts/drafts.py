"""A sentence turned into the rule it describes — as a proposal. The model is shown what exists and asked to fill in a rule
from it; what it returns is then checked by the same function that checks a rule typed into the form, so a draft can name
nothing the form could not. It never reaches the store: the operator saves, or does not."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import ValidationError

from .catalog import CatalogTool, number_fields, usable
from .contract import ConditionSource, Defect, DraftOut, EventSource, FilterTerm, RuleIn
from .gateway import Recipient
from .validation import Known, validate


class Unusable(Exception):
    """The model answered, and what it said cannot be read as a rule."""


@dataclass(frozen=True)
class Answer:
    payload: str
    model: str
    input_tokens: int
    output_tokens: int


class Drafter(Protocol):
    async def draft(self, system: str, sentence: str) -> Answer: ...


# What the model must return. Strict: every property present, nothing else, so the answer is a shape rather than a prose.
# Free-form maps (a tool's arguments, a filter's value) travel as JSON text because strict mode has no open objects.
_NULLABLE_TEXT = {"type": ["string", "null"]}
DRAFT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "understood", "name", "kind", "tool_name", "arguments_json", "field_path", "comparison", "threshold",
        "poll_interval_seconds", "event_type", "filter", "destination", "template", "cooldown_seconds", "mode", "problems",
    ],
    "properties": {
        "understood": {"type": "string"},
        "name": {"type": "string"},
        "kind": {"type": "string", "enum": ["condition", "event", "none"]},
        "tool_name": _NULLABLE_TEXT,
        "arguments_json": _NULLABLE_TEXT,
        "field_path": _NULLABLE_TEXT,
        "comparison": {"type": ["string", "null"], "enum": ["gt", "gte", "lt", "lte", "eq", None]},
        "threshold": _NULLABLE_TEXT,
        "poll_interval_seconds": {"type": ["integer", "null"]},
        "event_type": _NULLABLE_TEXT,
        "filter": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["attribute", "op", "value_json"],
                "properties": {
                    "attribute": {"type": "string"},
                    "op": {"type": "string", "enum": ["eq", "ne", "in", "gt", "gte", "lt", "lte", "contains"]},
                    "value_json": {"type": "string"},
                },
            },
        },
        "destination": _NULLABLE_TEXT,
        "template": _NULLABLE_TEXT,
        "cooldown_seconds": {"type": ["integer", "null"]},
        "mode": {"type": "string", "enum": ["once", "repeat"]},
        "problems": {"type": "array", "items": {"type": "string"}},
    },
}

INSTRUCTIONS = """You turn one sentence from the operator of a trading workstation into a notification rule. You are given what \
exists; a rule may use nothing else. Reply with the JSON the schema asks for and nothing besides.

Two kinds of rule:
- "condition": a read-only tool is asked for a number again and again, and the rule goes off when the number crosses the \
level. Fill tool_name, arguments_json (a JSON object text matching that tool's arguments), field_path (one of its \
number_fields), comparison, threshold (a number as text) and poll_interval_seconds (not below the minimum given). Leave event_type null.
- "event": something another part of the system announces (a film read, a post read, a team run finished). Fill event_type \
and filter (each term: attribute, op, value_json — the value as JSON text: "\\"text\\"", "8", "true", "[\\"a\\",\\"b\\"]"). Leave the \
condition fields null.
- "none": the sentence cannot be made into a rule from what exists.

Rules of conduct:
- Never invent a tool, field, event type, attribute, instrument or recipient. If the sentence names one that is not in the lists, \
say so in `problems` (in Polish, naming it) and leave the field null or the closest real one — do not substitute silently.
- An event rule's message comes from the event itself: `text` is the ready message the announcing part wrote, and each event type's `about` says what it holds (for a post, its content in Polish). When the sentence asks for the content or the details of what happened, leave template null (the default is that message) or use {text}; never say the content is unavailable and never rebuild the message from attributes alone.
- `problems` are for what the sentence asks and the lists cannot give. Never raise one about delivery, the Telegram channel or the bot.
- destination is a recipient's name from the list; null if the sentence names none.
- template is optional: null for the default message; otherwise text with {slots} among: for a condition rule, rule, value, \
threshold, comparison, tool, field and any scalar argument (e.g. {symbol}); for an event rule, rule, text, type and the event's attributes.
- cooldown_seconds: null for the default (900 for a condition, 0 for an event). "no more often than once an hour" is 3600.
- mode "once" only if the sentence says it is to tell a single time ("raz", "jednorazowo", "only once"); otherwise "repeat".
- name is a short label in Polish; `understood` is one sentence in Polish saying how you read the request.
- Prices: the "close" of a pair's latest candle is the price; "above" is gt, "below" is lt."""

CHANGE_INSTRUCTIONS = """The sentence is not a new rule: it is a change to the CURRENT RULE below. Return that rule in full, with exactly what the sentence changes and nothing else — the same tool, arguments, event type, filter, recipient, template, cool-down and mode unless the sentence says otherwise. `understood` says in one Polish sentence what was changed. A change the lists cannot support goes in `problems`, with the field left as it was."""


def system_prompt(
    known: Known, tools: list[CatalogTool], recipients: list[Recipient], symbols: list[str], current: RuleIn | None = None
) -> str:
    """The instructions, then everything that exists, trimmed to what the model needs to choose from. With `current`, the
    sentence is a change to that rule."""
    offered = [
        {
            "name": tool.name,
            "does": tool.description.strip().split("\n\n")[0][:240],
            "arguments": {
                name: {"type": prop.get("type") or [branch.get("type") for branch in prop.get("anyOf", [])], "description": prop.get("description", "")}
                for name, prop in tool.input_schema.get("properties", {}).items()
            },
            "required": tool.input_schema.get("required", []),
            "number_fields": number_fields(tool.output_schema),
        }
        for tool in tools
        if usable(tool) and number_fields(tool.output_schema)
    ]
    events = [
        {
            "name": name,
            "about": schema.get("description", ""),
            "attributes": {attr: prop.get("type") for attr, prop in schema.get("properties", {}).items()},
        }
        for name, schema in sorted(known.event_types.items())
    ]
    changing = [CHANGE_INSTRUCTIONS, "CURRENT RULE:\n" + current.model_dump_json()] if current else []
    return "\n\n".join(
        [
            INSTRUCTIONS,
            *changing,
            f"Minimum poll_interval_seconds: {known.min_interval_seconds}",
            "TOOLS (condition rules):\n" + json.dumps(offered, ensure_ascii=False),
            "EVENT TYPES (event rules):\n" + json.dumps(events, ensure_ascii=False),
            "RECIPIENTS:\n" + json.dumps([one.name for one in recipients], ensure_ascii=False),
            "TRACKED INSTRUMENTS (symbols):\n" + json.dumps(symbols[:120]),
        ]
    )


def convert(
    answer: Answer, *, recipients: list[Recipient], known: Known, symbols: list[str], current: RuleIn | None = None
) -> DraftOut:
    """The model's answer as a draft: a rule when it can be one, and every reason it cannot be right as it stands. For a
    change, what the model is not asked for (bot, hourly ceiling, switch) is the current rule's."""
    try:
        said = json.loads(answer.payload)
    except (TypeError, ValueError) as err:
        raise Unusable(f"the model's answer is not JSON: {answer.payload[:120]!r}") from err
    if not isinstance(said, dict) or "kind" not in said:
        raise Unusable(f"the model's answer is not a draft: {answer.payload[:120]!r}")

    notes: list[str] = []
    defects = [Defect(field="sentence", message=str(problem)) for problem in said.get("problems") or []]
    understood = str(said.get("understood") or "")
    if said["kind"] == "none":
        if not defects:
            defects.append(Defect(field="sentence", message="the sentence could not be made into a rule from what exists"))
        return DraftOut(understood=understood, rule=None, defects=defects, notes=notes)

    destination = said.get("destination")
    if not destination and current is not None:
        destination = current.destination
    if not destination:
        ready = [one for one in recipients if one.receives]
        if len(ready) == 1:
            destination = ready[0].name
            notes.append(f"No recipient was named; {destination!r} is the only one that receives, so it was chosen.")
        else:
            defects.append(Defect(field="destination", message="the sentence names nobody to tell — choose a recipient"))

    try:
        source = _source(said)
        rule = RuleIn(
            name=(said.get("name") or understood or "Nowa reguła")[:80],
            source=source,
            destination=destination or "?",
            template=said.get("template") or "",
            cooldown_seconds=said.get("cooldown_seconds"),
            mode=said.get("mode") or "repeat",
        )
    except (ValueError, ValidationError) as err:
        defects.append(Defect(field="sentence", message=f"the draft could not be read as a rule: {_first_line(err)}"))
        return DraftOut(understood=understood, rule=None, defects=defects, notes=notes)

    if current is not None:
        rule = rule.model_copy(
            update={
                "bot": current.bot if rule.destination == current.destination else None,
                "max_per_hour": current.max_per_hour,
                "enabled": current.enabled,
            }
        )
    if destination is None:
        # No recipient to check, and the one reason for it is already above; the form is given an empty field, not a placeholder.
        known = Known(known.tools, known.event_types, None, known.min_interval_seconds)
        rule = rule.model_copy(update={"destination": ""})
    defects += validate(rule, known)
    defects += _instrument_defects(rule, symbols)
    return DraftOut(understood=understood, rule=rule, defects=_unique(defects), notes=notes)


def _source(said: dict[str, Any]) -> ConditionSource | EventSource:
    if said["kind"] == "condition":
        arguments = json.loads(said.get("arguments_json") or "{}")
        if not isinstance(arguments, dict):
            raise ValueError("arguments_json is not an object")
        return ConditionSource(
            tool_name=said.get("tool_name") or "",
            arguments=arguments,
            field_path=said.get("field_path") or "",
            comparison=said.get("comparison") or "gt",
            threshold=said.get("threshold") or "",
            poll_interval_seconds=said.get("poll_interval_seconds") or 60,
        )
    terms = [
        FilterTerm(attribute=term["attribute"], op=term["op"], value=json.loads(term["value_json"]))
        for term in said.get("filter") or []
    ]
    return EventSource(event_type=said.get("event_type") or "", filter=terms)


def _instrument_defects(rule: RuleIn, symbols: list[str]) -> list[Defect]:
    """A pair the archive does not follow is a rule that watches nothing — which looks exactly like a rule whose level was
    not reached. Only where the archive was asked and answered."""
    source = rule.source
    if not symbols or not isinstance(source, ConditionSource):
        return []
    symbol = source.arguments.get("symbol")
    if isinstance(symbol, str) and symbol not in symbols:
        return [Defect(field="source.arguments.symbol", message=f"{symbol!r} is not an instrument the archive follows")]
    return []


def _unique(defects: list[Defect]) -> list[Defect]:
    seen: set[tuple[str, str]] = set()
    kept = []
    for defect in defects:
        if (defect.field, defect.message) not in seen:
            seen.add((defect.field, defect.message))
            kept.append(defect)
    return kept


def _first_line(error: Exception) -> str:
    return str(error).splitlines()[0] if str(error) else error.__class__.__name__
