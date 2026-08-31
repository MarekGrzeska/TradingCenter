"""The document both front ends generate their wire types from, built without starting anything.
The shaping is a copy of `polymarket_data/openapi.py`'s, and a copy gets its own tests."""

from __future__ import annotations

from social_data.openapi import document


def test_the_document_describes_every_shape_the_screens_read() -> None:
    # Also the check that it builds at all with nothing running: `Settings()` is constructed inside
    # `lifespan`, which this never enters.
    schema = document()
    assert schema["info"]["title"] == "social-data"

    schemas = schema["components"]["schemas"]
    for name in ("PostOut", "PostsOut", "StateOut", "SourceStateOut", "Problem"):
        assert name in schemas, name


def test_a_response_model_declares_every_field_it_always_sends() -> None:
    """A field with a default is not `required` to Pydantic, but this module answers with it regardless.
    Read raw a consumer gets `T | undefined` for a case that cannot happen, and a post is mostly those."""
    post = document()["components"]["schemas"]["PostOut"]

    assert "impact_score" in post["properties"]
    assert sorted(post["required"]) == sorted(post["properties"])
