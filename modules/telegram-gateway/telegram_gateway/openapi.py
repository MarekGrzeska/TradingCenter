"""The module's OpenAPI document, printed without starting anything, so reading it needs no database and no network.

No screen consumes this one — the gateway has no front end, and a notification is its screen. It is
published for the callers that write against the contract by hand, and for the same reason as every
other module's: a document that can only be obtained from a running deployment is not a contract.
"""

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
    """Mark every property of a response model as required, in place: pydantic's reading is right for what a caller
    sends and untrue for what this module answers with, which is serialised whole and mostly `X | None` fields."""
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


def document() -> dict[str, Any]:
    """The schema this module publishes, built in-process."""
    from .app import app  # local: importing at module level would close a cycle

    return require_response_fields(app.openapi())


def main() -> None:
    # Sorted keys so the same code always prints the same bytes: the generated TypeScript is committed
    # and compared, and a diff caused by dictionary ordering is noise nobody can act on.
    json.dump(document(), sys.stdout, indent=2, sort_keys=True, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
