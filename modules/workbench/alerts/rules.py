"""A stored rule as the wire says it, and the check that a rule is still what it was when it was written."""

from __future__ import annotations

from typing import Any

import asyncpg

from . import reach
from .contract import ConditionSource, Defect, EventSource, FilterTerm, RuleOut
from .reach import Reach
from .store import json_of
from .validation import filter_defects


def source_of(row: asyncpg.Record | dict[str, Any]) -> ConditionSource | EventSource:
    if row["kind"] == "condition":
        return ConditionSource(
            tool_name=row["tool_name"],
            arguments=json_of(row["arguments"]) or {},
            field_path=row["field_path"],
            comparison=row["comparison"],
            threshold=str(row["threshold"]),
            poll_interval_seconds=row["poll_interval_seconds"],
        )
    return EventSource(
        event_type=row["event_type"],
        filter=[FilterTerm(**term) for term in json_of(row["filter"]) or []],
    )


def out(row: asyncpg.Record, *, recipients: Reach | None) -> RuleOut:
    """`recipients` is who the door knows now and through which bots, or `None` when there is no door to ask: a rule is
    flagged for a recipient or a bot that is gone, not for one nobody could look up."""
    defects: list[Defect] = []
    if row["defect"]:
        defects.append(Defect(field="source.filter", message=row["defect"]))
    reaching = reach.defect_of(row["destination"], row["bot"], recipients)
    if reaching is not None:
        defects.append(reaching)
    return RuleOut(
        id=row["id"],
        name=row["name"],
        source=source_of(row),
        destination=row["destination"],
        bot=row["bot"],
        template=row["template"],
        cooldown_seconds=row["cooldown_seconds"],
        mode=row["mode"],
        max_per_hour=row["max_per_hour"],
        enabled=row["enabled"],
        disabled_reason=row["disabled_reason"],
        defects=defects,
        created_by=row["created_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        last_result=row["last_result"],
        last_checked_at=row["last_checked_at"],
        last_fired_at=row["last_fired_at"],
        next_check_at=row["next_check_at"],
    )


def drift(row: asyncpg.Record, schema: dict[str, Any]) -> str | None:
    """What a new schema took from a rule written against the old one, in a sentence — or `None` when it still fits. The
    rule is kept either way: a producer that renamed an attribute should not delete the operator's work."""
    source = source_of(row)
    assert isinstance(source, EventSource)
    found = filter_defects(source.filter, schema)
    if not found:
        return None
    return "; ".join(f"{defect.field}: {defect.message}" for defect in found)
