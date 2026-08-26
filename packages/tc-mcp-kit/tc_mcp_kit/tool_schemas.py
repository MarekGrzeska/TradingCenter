"""The published tool surface, without the scaffolding pydantic emits around it: a model reads every
description and both schemas in every turn. Measured 18 August 2026 across three modules: 64 416
characters before, 50 172 after, with every field, type, `format` and `required` entry surviving."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP


def slim_schema(schema: dict[str, Any], *, keep_defaults: bool = True) -> dict[str, Any]:
    """One JSON Schema, with the scaffolding removed. Returns a new object — the caller may
    still be holding the one it passed in."""
    return _walk(schema, keep_defaults)


def slim_tool_schemas(mcp: FastMCP, *, keep_input_defaults: bool = True) -> None:
    """Apply `slim_schema` to every tool already registered on this server. Called once at the end of
    `build_server`: a tool registered afterwards keeps its scaffolding."""
    # `_tool_manager` is private and there is no public accessor for a registered
    # tool's schemas; `mcp` is pinned exactly by all three consumers.
    for tool in mcp._tool_manager.list_tools():
        tool.parameters = slim_schema(tool.parameters, keep_defaults=keep_input_defaults)
        output_schema = tool.fn_metadata.output_schema
        if output_schema is None:
            continue
        tool.fn_metadata.output_schema = slim_schema(output_schema, keep_defaults=False)
        # `Tool.output_schema` is a `cached_property`, and a server whose tools were listed once
        # before this call would keep announcing the schema it cached.
        vars(tool).pop("output_schema", None)


# Keys whose *values* are maps of field name -> schema. Inside one, `title` and `default` are names a
# model chose: market-data's indicator catalogue publishes a parameter genuinely called `default`.
_NAME_MAPS = frozenset({"properties", "$defs", "patternProperties", "definitions"})


def _walk(node: Any, keep_defaults: bool, in_name_map: bool = False) -> Any:
    if isinstance(node, list):
        return [_walk(item, keep_defaults) for item in node]
    if not isinstance(node, dict):
        return node

    out: dict[str, Any] = {}
    for key, value in node.items():
        if not in_name_map:
            if key == "title":
                continue
            if key == "default" and not keep_defaults:
                continue
        # A field genuinely named `properties` is a field name, not a nesting level.
        out[key] = _walk(value, keep_defaults, key in _NAME_MAPS and not in_name_map)
    return out if in_name_map else _collapse_nullable(out)


def _collapse_nullable(node: dict[str, Any]) -> dict[str, Any]:
    """`anyOf` of bare types becomes a type list. A branch with anything else in it — a
    `$ref`, an `items`, a `format` — is a real union and stays one."""
    branches = node.get("anyOf")
    if not isinstance(branches, list) or not branches:
        return node
    if not all(isinstance(b, dict) and set(b) == {"type"} for b in branches):
        return node
    if "type" in node:
        return node

    types = [b["type"] for b in branches]
    collapsed = {k: v for k, v in node.items() if k != "anyOf"}
    collapsed["type"] = types[0] if len(types) == 1 else types
    return collapsed
