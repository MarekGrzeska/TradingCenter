from __future__ import annotations

from teams.openapi import _referenced, document, require_response_fields


def test_document_is_a_valid_looking_openapi_object() -> None:
    schema = document()
    assert schema["openapi"].startswith("3.")
    assert "/teams" in schema["paths"]


def test_the_document_describes_this_surface_and_not_the_one_beside_it() -> None:
    """`/health` and the conversation's routes belong to the process rather than to either
    surface, so the file the terminal generates from this describes teams alone."""
    paths = document()["paths"]
    assert "/health" not in paths
    assert "/sessions" not in paths
    # Where this surface's two collided with the conversation's, its own moved.
    assert "/teams/models" in paths
    assert "/teams/usage" in paths


def test_document_is_the_same_object_on_repeat_calls() -> None:
    # `require_response_fields` mutates in place, so two callers reading two objects that
    # merely look alike is a way for one's edit to be invisible to the other. FastAPI's own
    # cache used to give this; the module keeps it now that the document is built from an
    # application of its own.
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
