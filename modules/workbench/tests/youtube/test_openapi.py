"""The document the terminal generates its wire types from, built without starting anything."""

from __future__ import annotations

from youtube_data.openapi import document


def test_the_document_builds_with_nothing_running() -> None:
    # `Settings()` is constructed inside `lifespan`, which this never enters.
    assert document()["info"]["title"] == "youtube-data"
