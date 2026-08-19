"""The module's OpenAPI document, printed without starting anything.

A twin of `market_data/openapi.py`, minus the WebSocket message hoisting that file also
does: this module has no subscription with messages FastAPI cannot describe on its own.
If one arrives later, it is the same pattern — hang the models into `components.schemas`
by hand, the way `market_data.hub`'s `Snapshot`/`CandleChange` are.

FastAPI builds the document from the Pydantic models in `contract.py` — it is a property
of the code, not of a running process — so nothing here opens a connection pool, reaches
for market-mcp, or reads a setting. `Settings()` is constructed inside `lifespan`, which
this never enters.

    uv run python -m teams.openapi > schema.json
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
    """Mark every property of a response model as required, in place.

    Pydantic leaves a field with a default out of `required`, which is right for
    something a caller *sends*: omitting it means "use the default". For something this
    module *answers with* it is simply untrue — a `TeamOut` always carries
    `latest_revision`, never omits it. Left alone as an internal wart it would cost
    nothing; it stops being internal the moment a consumer generates types from it, where
    every optional field arrives as `T | undefined` for a case that cannot happen.

    Request bodies keep Pydantic's reading, so the two are told apart by reachability
    rather than by a hand-kept list — a list would rot the first time a model moved
    sides.
    """
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


# Built once per process. `require_response_fields` mutates in place and every caller is
# free to read the result, so handing out two objects that only look alike is a way for one
# caller's edit to be invisible to the next — which is what FastAPI's own `openapi_schema`
# cache used to prevent while this read a running application's document.
_document: dict[str, Any] | None = None


def document() -> dict[str, Any]:
    """The schema this surface publishes, built in-process.

    A FastAPI of its own rather than the process's, and the difference is the point: the
    generated TypeScript describes *this* surface, not the conversation's beside it. The
    routers and their prefixes come from `surface.include`, the same function
    `workbench/app.py` calls, so a path published here is a path served there — there is no
    second list of prefixes to keep in step. What is *not* here is `/health`: that belongs
    to the process, not to either surface.
    """
    global _document
    if _document is None:
        from fastapi import FastAPI

        from .surface import include

        app = FastAPI(title="TradingCenter · teams", version="0.1.0")
        include(app)
        _document = require_response_fields(app.openapi())
    return _document


def main() -> None:
    # Sorted keys so the same code always prints the same bytes: the generated
    # TypeScript is committed and compared, and a diff caused by dictionary ordering
    # would be noise nobody can act on.
    json.dump(document(), sys.stdout, indent=2, sort_keys=True, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
