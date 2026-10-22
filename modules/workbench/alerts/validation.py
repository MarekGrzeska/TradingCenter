"""The refusals that keep a rule from being saved when it could never work. Pure: it is given what is known and returns
what is wrong, so the same function answers the form on save, the draft before it is shown, and an announcement that
changed a schema under a rule already written."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator

from . import reach, template
from .catalog import NUMBER_TYPES, CatalogTool, json_type, number_fields, usable
from .contract import ConditionSource, Defect, EventSource, FilterTerm, RuleIn
from .reach import Reach

# Which comparisons an attribute of each type can take. A number is not compared with `contains`, and a list is not
# compared with `gt` — the form offers only these, and the server refuses the rest.
OPS_BY_TYPE: dict[str, tuple[str, ...]] = {
    "string": ("eq", "ne", "in"),
    "number": ("eq", "ne", "gt", "gte", "lt", "lte", "in"),
    "integer": ("eq", "ne", "gt", "gte", "lt", "lte", "in"),
    "boolean": ("eq", "ne"),
    "array": ("contains",),
}

CONDITION_RESERVED = ("rule", "value", "threshold", "comparison", "tool", "field")
EVENT_RESERVED = ("rule", "text", "type")


@dataclass(frozen=True)
class Known:
    """What exists, as the process knows it right now."""

    tools: Mapping[str, CatalogTool]
    event_types: Mapping[str, dict[str, Any]]
    # `None` when there is no door to Telegram to ask — a recipient cannot be checked, and the package says it delivers
    # nothing. A rule written then is not refused for a thing nobody could verify.
    destinations: Reach | None
    min_interval_seconds: int


def validate(rule: RuleIn, known: Known) -> list[Defect]:
    defects: list[Defect] = []
    source = rule.source
    if isinstance(source, ConditionSource):
        defects += _condition(source, known)
    else:
        defects += _event(source, known)

    reaching = reach.defect_of(rule.destination, rule.bot, known.destinations)
    if reaching is not None:
        defects.append(reaching)

    allowed = template_slots(rule, known)
    for slot in template.unknown_slots(effective_template(rule), allowed):
        defects.append(Defect(field="template", message=f"{{{slot}}} is not something this rule can fill in; it can fill {', '.join(sorted(allowed))}"))
    return defects


def effective_template(rule: RuleIn) -> str:
    if rule.template.strip():
        return rule.template
    return template.CONDITION_DEFAULT if isinstance(rule.source, ConditionSource) else template.EVENT_DEFAULT


def effective_cooldown(rule: RuleIn) -> int:
    if rule.cooldown_seconds is not None:
        return rule.cooldown_seconds
    return 900 if isinstance(rule.source, ConditionSource) else 0


def template_slots(rule: RuleIn, known: Known) -> list[str]:
    """What a message of this rule can say: the fixed names of its kind, and the scalars it was given."""
    source = rule.source
    if isinstance(source, ConditionSource):
        extras = [
            name for name, value in source.arguments.items() if isinstance(value, str | int | float | bool) and name.isidentifier()
        ]
        return [*CONDITION_RESERVED, *(name for name in extras if name not in CONDITION_RESERVED)]
    schema = known.event_types.get(source.event_type, {})
    attributes = [name for name in schema.get("properties", {}) if name not in EVENT_RESERVED]
    return [*EVENT_RESERVED, *attributes]


def _condition(source: ConditionSource, known: Known) -> list[Defect]:
    defects: list[Defect] = []
    tool = known.tools.get(source.tool_name)
    if tool is None:
        return [Defect(field="source.tool_name", message=f"no tool named {source.tool_name!r} is offered by this process")]
    if not usable(tool):
        return [Defect(field="source.tool_name", message=f"{source.tool_name!r} is not a tool that only reads, and a rule may only read")]

    properties = tool.input_schema.get("properties", {})
    for name in source.arguments:
        if name not in properties:
            defects.append(Defect(field=f"source.arguments.{name}", message=f"{source.tool_name!r} takes no argument {name!r}"))
    known_arguments = {name: value for name, value in source.arguments.items() if name in properties}
    for error in Draft202012Validator(tool.input_schema).iter_errors(known_arguments):
        where = ".".join(str(part) for part in error.absolute_path)
        defects.append(Defect(field=f"source.arguments.{where}" if where else "source.arguments", message=error.message))

    # A tool that publishes no answer schema cannot be checked, and is let through: refusing it would refuse the tool.
    if tool.output_schema:
        numbers = number_fields(tool.output_schema)
        if source.field_path not in numbers:
            offered = ", ".join(numbers) if numbers else "none"
            defects.append(
                Defect(
                    field="source.field_path",
                    message=f"{source.field_path!r} is not a number in the answer of {source.tool_name!r}; numbers there: {offered}",
                )
            )

    if source.poll_interval_seconds < known.min_interval_seconds:
        defects.append(
            Defect(
                field="source.poll_interval_seconds",
                message=f"a rule may look no more often than every {known.min_interval_seconds} s; got {source.poll_interval_seconds}",
            )
        )
    return defects


def _event(source: EventSource, known: Known) -> list[Defect]:
    schema = known.event_types.get(source.event_type)
    if schema is None:
        return [Defect(field="source.event_type", message=f"nobody has announced an event type {source.event_type!r}")]
    return filter_defects(source.filter, schema)


def filter_defects(terms: list[FilterTerm], schema: dict[str, Any]) -> list[Defect]:
    """What is wrong with these terms against this schema. Also the check an announcement makes of every rule already
    written for the type, so the wording is the same on the form and on the list."""
    defects: list[Defect] = []
    properties = schema.get("properties", {})
    defs = {**schema.get("$defs", {}), **schema.get("definitions", {})}
    for index, term in enumerate(terms):
        where = f"source.filter.{index}"
        prop = properties.get(term.attribute)
        if prop is None:
            offered = ", ".join(properties) or "none"
            defects.append(Defect(field=f"{where}.attribute", message=f"events of this type carry no {term.attribute!r}; they carry {offered}"))
            continue
        kind = json_type(prop, defs)
        allowed = OPS_BY_TYPE.get(kind or "")
        if allowed is None:
            defects.append(Defect(field=f"{where}.attribute", message=f"{term.attribute!r} is not something a rule can compare"))
            continue
        if term.op not in allowed:
            defects.append(Defect(field=f"{where}.op", message=f"{term.attribute!r} is a {kind}; it can be compared with {', '.join(allowed)}, not {term.op}"))
            continue
        problem = _value_problem(term, kind or "", prop, defs)
        if problem:
            defects.append(Defect(field=f"{where}.value", message=problem))
    return defects


def _value_problem(term: FilterTerm, kind: str, prop: dict[str, Any], defs: dict[str, Any]) -> str | None:
    value = term.value
    if term.op == "in":
        if not isinstance(value, list):
            return "`in` takes a list of values"
        wanted = kind
        if wanted in NUMBER_TYPES:
            return None if all(_is_number_text(one) for one in value) else "`in` on a number takes numbers"
        return None
    if isinstance(value, list):
        return f"{term.op} takes one value, not a list"
    if term.op == "contains":
        items = prop.get("items") if isinstance(prop.get("items"), dict) else None
        item_kind = json_type(items, defs) if items else "string"
        return None if _fits(value, item_kind or "string") else f"a member of this list is a {item_kind}"
    return None if _fits(value, kind) else f"{term.attribute!r} is a {kind}; {value!r} is not"


def _fits(value: Any, kind: str) -> bool:
    if kind in NUMBER_TYPES:
        return isinstance(value, int | float) and not isinstance(value, bool)
    if kind == "boolean":
        return isinstance(value, bool)
    return isinstance(value, str)


def _is_number_text(value: Any) -> bool:
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True
