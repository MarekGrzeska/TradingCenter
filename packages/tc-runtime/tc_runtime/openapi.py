"""Two things every module's `openapi.py` did identically: correct what pydantic says is optional in
a response, and print the document the same bytes every time. What each module publishes — and what
it hoists into the document that FastAPI cannot describe — stays in the module."""

from __future__ import annotations

import json
import sys
from typing import Any


def _referenced(node: Any, into: set[str]) -> None:
    """Every component name reachable from `node`, following `$ref` transitively."""
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            into.add(ref.rsplit("/", 1)[1])
        for value in node.values():
            _referenced(value, into)
    elif isinstance(node, list):
        for value in node:
            _referenced(value, into)


def require_response_fields(schema: dict[str, Any]) -> dict[str, Any]:
    """Mark every property of a response model as required, in place: pydantic's reading is right for
    what a caller sends and untrue for what a module answers with, which is serialised whole and
    mostly `X | None` fields. Request bodies keep pydantic's reading, told apart by reachability from
    a `requestBody` rather than by a list somebody has to maintain."""
    components = schema.get("components", {}).get("schemas", {})
    from_requests: set[str] = set()
    for path in schema.get("paths", {}).values():
        for operation in path.values():
            if isinstance(operation, dict) and "requestBody" in operation:
                _referenced(operation["requestBody"], from_requests)
    # A component reached from a request body may hold more of them.
    frontier = set(from_requests)
    while frontier:
        nested: set[str] = set()
        for name in frontier:
            _referenced(components.get(name, {}), nested)
        frontier = nested - from_requests
        from_requests |= nested

    for name, model in components.items():
        properties = model.get("properties")
        if not properties or name in from_requests:
            continue
        model["required"] = sorted(properties)
    return schema


def print_document(document: dict[str, Any]) -> None:
    """To stdout, and byte-for-byte the same for the same document. Sorted keys because the generated
    TypeScript is committed and compared, and a diff caused by dictionary ordering is noise nobody
    can act on."""
    json.dump(document, sys.stdout, indent=2, sort_keys=True, ensure_ascii=False)
    sys.stdout.write("\n")
