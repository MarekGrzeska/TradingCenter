"""The module's OpenAPI document, printed without starting anything — the terminal's contract is
generated from here. Augmented with the WebSocket's message models, which FastAPI cannot describe."""

from __future__ import annotations

import json
import sys
from typing import Any

from pydantic import TypeAdapter

# Import from `hub` rather than `app`: this module is imported *by* `app`, so reaching back for it
# would close a cycle.
from .hub import CandleChange, Snapshot

# Where the WebSocket's message models are hung in the document. Not reachable by any path, which is
# honest, but part of the published contract a generator walking `components.schemas` will find.
STREAM_MESSAGES: dict[str, type] = {
    "Snapshot": Snapshot,
    "CandleChange": CandleChange,
}


def add_stream_messages(schema: dict[str, Any]) -> dict[str, Any]:
    """Merge the subscription's message models into an OpenAPI document, in place. Idempotent:
    FastAPI hands back the same cached object every time, so this must leave an augmented one alone."""
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    for name, model in STREAM_MESSAGES.items():
        # `ref_template` is what makes this mergeable at all: Pydantic would otherwise point its
        # references at `#/$defs/...`, which means nothing inside an OpenAPI document.
        built = TypeAdapter(model).json_schema(ref_template="#/components/schemas/{model}")
        for nested_name, nested in built.pop("$defs", {}).items():
            components.setdefault(nested_name, nested)
        components.setdefault(name, built)
    return schema


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
    """Mark every property of a response model as required, in place. Pydantic's reading is right for
    something a caller sends and untrue for something this module answers with, which is serialised whole."""
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
    from .app import app  # local: `app` imports this module

    return app.openapi()


def main() -> None:
    # Sorted keys so the same code always prints the same bytes: the generated TypeScript is
    # committed and compared, and a diff caused by dictionary ordering is noise nobody can act on.
    json.dump(document(), sys.stdout, indent=2, sort_keys=True, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
