from __future__ import annotations

from teams.openapi import document


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
