"""The module's OpenAPI document, printed without starting anything — the terminal's contract is
generated from here. Augmented with the WebSocket's message models, which FastAPI cannot describe."""

from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter
from tc_runtime.openapi import print_document

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


def document() -> dict[str, Any]:
    """The schema this module publishes, built in-process."""
    from .app import app  # local: `app` imports this module

    return app.openapi()


def main() -> None:
    print_document(document())


if __name__ == "__main__":
    main()
