"""The module's OpenAPI document, printed without starting anything — a twin of market-data's, minus the WebSocket
hoisting, since this module has no subscription FastAPI cannot describe: `uv run python -m teams.openapi`."""

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
    """Mark every property of a response model as required, in place: pydantic's reading is right for what a caller sends
    and untrue for what this answers with. Request bodies keep it, told apart by reachability rather than a list."""
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


# Built once per process. `require_response_fields` mutates in place and every caller reads the result, so
# handing out two objects that only look alike is a way for one caller's edit to be invisible to the next.
_document: dict[str, Any] | None = None


def document() -> dict[str, Any]:
    """The schema this surface publishes, built in-process from a FastAPI of its own, so the generated TypeScript
    describes *this* surface. `/health` is not here: it belongs to the process, not to either surface."""
    global _document
    if _document is None:
        from fastapi import FastAPI

        from .surface import include

        app = FastAPI(title="TradingCenter · teams", version="0.1.0")
        include(app)
        _document = require_response_fields(app.openapi())
    return _document


def main() -> None:
    # Sorted keys so the same code always prints the same bytes: the generated TypeScript is committed and
    # compared, and a diff caused by dictionary ordering is noise nobody can act on.
    json.dump(document(), sys.stdout, indent=2, sort_keys=True, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
