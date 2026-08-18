"""The published tool surface, without the scaffolding pydantic emits around it.

A model reads every tool's description and both its schemas in *every* turn, so the size
of what a server announces is a running cost rather than a detail. Measured on
18 August 2026 across the three MCP modules: 64 416 characters, 15 134 tokens
(`cl100k_base`) for one turn of the agent, which mounts all three.

Three keys carry no information a model does not already have from the schema itself:

- `title` — pydantic writes one for every field and every model, and it is the field's own
  name in title case. 10 733 characters of the measurement above;
- `anyOf` whose branches are bare types — `[{"type": "string"}, {"type": "null"}]` says
  what `"type": ["string", "null"]` says in half the characters. A branch carrying anything
  more than a type (a `$ref`, a `format`, an `items`) is left alone;
- `default` in an *output* schema — a default is what happens when the caller omits a
  field, and a model never constructs a reply. On the input side it stays: there it is the
  answer to "what if I don't pass this".

Nothing that changes what is allowed is touched: every field, its type, its `format`, its
`description` and the `required` list survive. `outputSchema` itself is not dropped, and
that is deliberate — the lowlevel server validates every structured reply against it, and
that validation is the only thing that has ever caught an alias mismatch between the
schema and the reply (`WindowedOut` in market-mcp).

Measured after: 50 172 characters, 11 718 tokens. See
`openspec/changes/hot-paths-stop-paying-twice/design.md`, D2, for the table.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP


def slim_schema(schema: dict[str, Any], *, keep_defaults: bool = True) -> dict[str, Any]:
    """One JSON Schema, with the scaffolding removed. Returns a new object — the caller may
    still be holding the one it passed in."""
    return _walk(schema, keep_defaults)


def slim_tool_schemas(mcp: FastMCP, *, keep_input_defaults: bool = True) -> None:
    """Apply `slim_schema` to every tool already registered on this server.

    Called once at the end of `build_server`, after the tools are in — a tool registered
    afterwards keeps its scaffolding, which the module's own surface-ceiling test is what
    catches.
    """
    # `_tool_manager` is private and there is no public accessor for a registered
    # tool's schemas; `mcp` is pinned exactly by all three consumers.
    for tool in mcp._tool_manager.list_tools():
        tool.parameters = slim_schema(tool.parameters, keep_defaults=keep_input_defaults)
        output_schema = tool.fn_metadata.output_schema
        if output_schema is None:
            continue
        tool.fn_metadata.output_schema = slim_schema(output_schema, keep_defaults=False)
        # `Tool.output_schema` is a `cached_property` over the line above, and a server
        # whose tools were listed once before this call would otherwise keep announcing
        # the schema it cached. Dropping the cache leaves `fn_metadata` as the one source.
        vars(tool).pop("output_schema", None)


def _walk(node: Any, keep_defaults: bool) -> Any:
    if isinstance(node, list):
        return [_walk(item, keep_defaults) for item in node]
    if not isinstance(node, dict):
        return node

    out: dict[str, Any] = {}
    for key, value in node.items():
        if key == "title":
            continue
        if key == "default" and not keep_defaults:
            continue
        out[key] = _walk(value, keep_defaults)
    return _collapse_nullable(out)


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
