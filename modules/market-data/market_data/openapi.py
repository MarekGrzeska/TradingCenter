"""The module's OpenAPI document, printed without starting anything.

The terminal's view of this contract is generated from here rather than copied by hand
(`generate-terminal-contract-from-openapi`). What made that possible is that FastAPI
builds the document from the Pydantic models in `contract.py` — it is a property of the
code, not of a running process — so nothing here opens a connection pool, reaches for a
gateway, or reads a setting. `Settings()` is constructed inside `lifespan`, which this
never enters.

That matters more than it looks. Regenerating the contract against a *running* server
would mean regenerating it needs a database, an account and a network, which means it
would not be run, which is exactly how the two copies of a contract drift apart in the
first place.

    uv run python -m market_data.openapi > schema.json

The document is also **augmented** here, and `app.py` publishes the augmented one so
there is only ever one. FastAPI describes routes, and a WebSocket has none — no request
body, no response model, nothing OpenAPI has a place for — so `/ws/candles` appears in
neither `paths` nor `components`. Its messages are Pydantic models all the same, and they
are the most drift-prone part of the whole contract: a chart reads every candle through
them. Leaving them as the one shape still copied by hand would have kept the defect this
change exists to remove, in the place it would hurt most.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from pydantic import TypeAdapter

# Import from `hub` rather than `app`: this module is imported *by* `app`, so reaching
# back for it would close a cycle. `main()` takes the app, lazily, at the one moment it
# actually needs it.
from .hub import CandleChange, Snapshot

# Where the WebSocket's message models are hung in the document. They are not reachable
# by any path, which is honest — nothing serves them over HTTP — but they are part of the
# published contract and a generator walking `components.schemas` will find them.
STREAM_MESSAGES: dict[str, type] = {
    "Snapshot": Snapshot,
    "CandleChange": CandleChange,
}


def add_stream_messages(schema: dict[str, Any]) -> dict[str, Any]:
    """Merge the subscription's message models into an OpenAPI document, in place.

    Idempotent: FastAPI caches its document on the app and hands back the same object
    every time, so this runs against an already-augmented dict on every call after the
    first and must leave it alone.
    """
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    for name, model in STREAM_MESSAGES.items():
        # `ref_template` is what makes this mergeable at all: Pydantic would otherwise
        # point its references at `#/$defs/...`, which means nothing inside an OpenAPI
        # document. Asked for the OpenAPI spelling, the nested models it pulls in — a
        # candle, a resolution — land as ordinary components alongside FastAPI's own.
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
    """Mark every property of a response model as required, in place.

    Pydantic leaves a field with a default out of `required`, which is right for something
    a caller *sends*: omitting it means "use the default". For something this module
    *answers with* it is simply untrue. FastAPI serialises a response model whole — a
    `TrackedPairOut` always carries `earliest_candle`, as `null` when there is none — so a
    schema calling it optional describes a response this module never sends.

    Left alone as an internal wart it would cost nothing. It stops being internal the
    moment a consumer generates types from it: every optional field arrives as
    `T | undefined`, and the consumer either writes `undefined` handling for a case that
    cannot happen, or asserts it away and loses the checking it generated types to get.

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
    from .app import app  # local: `app` imports this module

    return app.openapi()


def main() -> None:
    # Sorted keys so the same code always prints the same bytes: the generated TypeScript
    # is committed and compared, and a diff caused by dictionary ordering would be noise
    # nobody can act on.
    json.dump(document(), sys.stdout, indent=2, sort_keys=True, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
