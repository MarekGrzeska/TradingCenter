from __future__ import annotations

from teams.openapi import _referenced, document, require_response_fields


def test_document_is_a_valid_looking_openapi_object() -> None:
    schema = document()
    assert schema["openapi"].startswith("3.")
    assert "/health" in schema["paths"]


def test_document_is_the_same_object_on_repeat_calls() -> None:
    # FastAPI caches the augmented schema on the app — two calls must not run the
    # augmentation twice (`require_response_fields` mutates in place, and running it
    # again on its own output is harmless but wasted work if it happened).
    first = document()
    second = document()
    assert first is second


def test_require_response_fields_is_idempotent() -> None:
    schema = document()
    once = require_response_fields(schema)
    twice = require_response_fields(once)
    assert once == twice


def test_referenced_follows_refs_transitively() -> None:
    node = {"a": {"$ref": "#/components/schemas/Foo"}, "b": [{"$ref": "#/components/schemas/Bar"}]}
    into: set[str] = set()
    _referenced(node, into)
    assert into == {"Foo", "Bar"}


def test_referenced_ignores_refs_outside_components_schemas() -> None:
    into: set[str] = set()
    _referenced({"$ref": "#/definitions/Foo"}, into)
    assert into == set()
