"""The document the terminal generates its wire types from, built without starting anything."""

from __future__ import annotations

from youtube_data.openapi import document


def test_the_document_builds_with_nothing_running() -> None:
    # `Settings()` is constructed inside `lifespan`, which this never enters.
    assert document()["info"]["title"] == "youtube-data"


def test_the_document_describes_every_shape_the_screen_reads() -> None:
    schemas = document()["components"]["schemas"]

    for name in ("VideoOut", "VideosOut", "ReadingOut", "StateOut", "ChannelOut", "TopicOut", "Problem"):
        assert name in schemas, name


def test_a_response_model_declares_every_field_it_always_sends() -> None:
    """A field with a default is not `required` to Pydantic, but this package answers with it regardless. Read raw, a
    consumer gets `T | undefined` for a case that cannot happen — and a film is mostly optional-looking fields."""
    film = document()["components"]["schemas"]["VideoOut"]

    assert "reading" in film["properties"] and "simulated" in film["properties"]
    assert sorted(film["required"]) == sorted(film["properties"])
