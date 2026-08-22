"""The module's OpenAPI document, printed without starting anything.

The terminal generates its view of this contract from here rather than copying it by hand,
the way it already does for `market-data` and the workbench's teams surface. What makes
that possible is that FastAPI builds the document from the Pydantic models in
`contract.py` — a property of the code, not of a running process — so nothing here opens a
connection pool, reaches for Polymarket or reads a setting. `Settings()` is constructed
inside `lifespan`, which this never enters.

    uv run python -m polymarket_data.openapi > schema.json

That matters more than it looks: regenerating against a *running* server would mean
regenerating needs a database and a network, which means it would not be run — which is
exactly how two copies of a contract drift apart.

**There is no consumer of these types yet**, and that is deliberate rather than an
oversight. The terminal's subpage is a separate change; what this buys before it exists is
that `contract:check` fails the day this contract moves, so the subpage starts against
types that are true rather than against a file born stale.
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

    The twin of `market_data/openapi.py`'s function of the same name, copied rather than
    shared because no module imports another — and the reason it exists is identical, which
    is why it is worth stating again rather than pointing at. Pydantic leaves a field with a
    default out of `required`, which is right for something a caller *sends*: omitting it
    means "use the default". For something this module *answers with* it is simply untrue.
    FastAPI serialises a response model whole — an `OutcomeOut` always carries `price`, as
    `null` when nothing has been collected — so a schema calling it optional describes a
    response this module never sends.

    This contract is mostly such fields: a price, the moment it was taken, the baseline a
    change was measured from, all `X | None`. Generated as `T | undefined` they would make a
    consumer either write handling for a case that cannot happen or assert it away and lose
    the checking it generated types to get.

    Request bodies keep Pydantic's reading, so the two are told apart by reachability rather
    than by a hand-kept list — a list would rot the first time a model moved sides.
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
    from .app import app  # local: importing at module level would close a cycle

    return require_response_fields(app.openapi())


def main() -> None:
    # Sorted keys so the same code always prints the same bytes: the generated TypeScript is
    # committed and compared, and a diff caused by dictionary ordering would be noise nobody
    # can act on.
    json.dump(document(), sys.stdout, indent=2, sort_keys=True, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
