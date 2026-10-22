"""What a rule can be built from, as the process offers it: the read-only tools of its packages, and what each can
answer with. Nothing here imports a package — the assembly hands over an object that fits `ToolSource`."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

NUMBER_TYPES = ("number", "integer")


@dataclass(frozen=True)
class CatalogTool:
    name: str
    description: str
    source: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None
    read_only: bool | None


@dataclass(frozen=True)
class ToolOutcome:
    kind: Literal["ok", "refused", "unavailable"]
    text: str


class ToolSource(Protocol):
    """The tool surface of the process, called as functions. `tools` is every tool there is, writing ones included — a
    rule that names one is refused by name rather than by 'unknown'."""

    async def tools(self) -> list[CatalogTool]: ...

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolOutcome: ...


def usable(tool: CatalogTool) -> bool:
    """Only a tool that says it reads. A tool that does not say is not trusted to."""
    return tool.read_only is True


def json_type(schema: dict[str, Any], defs: dict[str, Any]) -> str | None:
    """The one type a property has once `null` is set aside — `float | None` is a number that may be missing."""
    resolved = _resolve(schema, defs)
    declared = resolved.get("type")
    if isinstance(declared, list):
        declared = next((one for one in declared if one != "null"), None)
    if isinstance(declared, str):
        return declared
    for branch in resolved.get("anyOf", []) + resolved.get("oneOf", []):
        found = json_type(branch, defs)
        if found not in (None, "null"):
            return found
    if "properties" in resolved:
        return "object"
    return None


def _resolve(schema: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    """Follows `$ref` and merges `allOf` — Pydantic writes a nested model as one or the other."""
    seen = 0
    while "$ref" in schema and seen < 16:
        seen += 1
        schema = defs.get(schema["$ref"].rsplit("/", 1)[-1], {})
    for part in schema.get("allOf", []):
        schema = {**_resolve(part, defs), **{k: v for k, v in schema.items() if k != "allOf"}}
    return schema


def number_fields(output_schema: dict[str, Any] | None) -> list[str]:
    """Dotted paths into a tool's answer that hold a number, in the notation a rule's `field_path` uses: object keys by
    name, and a list by the index of its first item. A list is read at its head because a rule compares one value, and
    'the first' is the one place a list has a stable address."""
    if not output_schema:
        return []
    defs = {**output_schema.get("$defs", {}), **output_schema.get("definitions", {})}
    found: list[str] = []
    _walk(output_schema, defs, "", found, depth=0)
    return found


def _walk(schema: dict[str, Any], defs: dict[str, Any], prefix: str, found: list[str], *, depth: int) -> None:
    if depth > 6:
        return
    resolved = _resolve(schema, defs)
    kind = json_type(resolved, defs)
    if kind in NUMBER_TYPES:
        if prefix:
            found.append(prefix)
        return
    if kind == "object":
        for name, child in resolved.get("properties", {}).items():
            _walk(child, defs, f"{prefix}.{name}" if prefix else name, found, depth=depth + 1)
    elif kind == "array":
        items = resolved.get("items")
        if isinstance(items, dict):
            _walk(items, defs, f"{prefix}.0" if prefix else "0", found, depth=depth + 1)
