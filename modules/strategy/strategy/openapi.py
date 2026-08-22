"""The module's OpenAPI document, printed without starting anything.

The terminal generates its view of this contract from here rather than copying it by hand,
as it already does for `market-data`, the workbench's teams surface and `polymarket-data`.
What makes that possible is that FastAPI builds the document from the Pydantic models in
`contract.py` — a property of the code, not of a running process — so nothing here opens a
pool, reaches the archive or reads a setting. `Settings()` is built inside `lifespan`,
which this never enters.

    uv run python -m strategy.openapi > schema.json

Regenerating against a *running* server would mean regenerating needs a database and a
network, which means it would not be run — which is exactly how two copies of a contract
drift apart.
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

    The third copy of this function in this repository, and copied rather than shared for
    the reason no module imports another. The reason it exists is identical every time, so
    it is worth stating again rather than pointing at: Pydantic leaves a field with a
    default out of `required`, which is right for something a caller *sends* — omitting it
    means "use the default" — and simply untrue for something a module *answers with*.
    FastAPI serialises a response model whole.

    This contract is mostly such fields. A refusal carries `reason` and no levels; a trade
    carries levels and often no `reason`; `reason_kind` is null on a trade. Generated as
    `T | undefined` they would make a consumer either handle a case that cannot happen or
    assert it away and lose the checking it generated types to get — and here the values in
    question are a stop and a target, where "absent" and "null" reading the same would be a
    consumer that cannot tell a missing price from one that was never set.

    Request bodies keep Pydantic's reading, so the two are told apart by reachability
    rather than by a hand-kept list — a list would rot the first time a model moved sides.
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


def document() -> dict[str, Any]:
    """The schema this module publishes, built in-process."""
    from .app import create_app  # local: importing at module level would close a cycle

    return require_response_fields(create_app().openapi())


def main() -> None:
    # Sorted keys so the same code always prints the same bytes: the generated TypeScript is
    # committed and compared, and a diff caused by dictionary ordering would be noise nobody
    # can act on.
    json.dump(document(), sys.stdout, indent=2, sort_keys=True, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
