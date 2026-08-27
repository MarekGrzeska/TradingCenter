"""The document the terminal generates its types from, built without starting anything. The shaping below
is a copy of `market_data/openapi.py`'s, and a copy gets its own tests."""

from __future__ import annotations

from polymarket_data.openapi import document


def test_the_document_describes_every_shape_the_terminal_reads() -> None:
    # Also the check that it builds at all with nothing running: `Settings()` is constructed inside
    # `lifespan`, which this never enters.
    schema = document()
    assert schema["info"]["title"] == "polymarket-data"

    schemas = schema["components"]["schemas"]
    for name in ("TrackedEventOut", "MarketOut", "OutcomeOut", "HistoryOut", "ChangesOut"):
        assert name in schemas, name


def test_a_response_model_declares_every_field_it_always_sends() -> None:
    """A field with a default is not `required` to Pydantic, but this module answers with it regardless.
    Read raw a consumer gets `T | undefined` for a case that cannot happen, and this contract is mostly those."""
    outcome = document()["components"]["schemas"]["OutcomeOut"]

    assert "price" in outcome["properties"]
    assert sorted(outcome["required"]) == sorted(outcome["properties"])


def test_a_request_model_keeps_its_optional_fields_optional() -> None:
    """The other half, and why this is not a blanket rule: omitting a field a caller *sends* is how its
    default gets used. `TrackRequest.group` is exactly that."""
    request = document()["components"]["schemas"]["TrackRequest"]

    assert "group" in request["properties"]
    assert sorted(request.get("required", [])) != sorted(request["properties"])
