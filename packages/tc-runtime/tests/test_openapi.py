"""The rule pydantic gets wrong for a response, tested once here rather than in each of the six
modules that publish a document. What each of them publishes is its own test."""

from __future__ import annotations

from tc_runtime.openapi import require_response_fields


def document_with(schema: dict) -> dict:
    return {"components": {"schemas": schema}, "paths": {}}


def test_a_response_model_has_every_property_required() -> None:
    """Pydantic marks `X | None` optional. Serialised whole, it is always there — and a generated
    client that believes otherwise makes every field a `| undefined` nobody needs to handle."""
    schema = require_response_fields(
        document_with({"Candle": {"properties": {"close": {}, "open": {}}}})
    )
    assert schema["components"]["schemas"]["Candle"]["required"] == ["close", "open"]


def test_a_request_model_keeps_pydantics_reading() -> None:
    """What a caller sends really can omit an optional field, and that is the half of the document
    pydantic is right about. Reachability from a `requestBody` is what tells them apart."""
    schema = {
        "components": {"schemas": {"NewWatch": {"properties": {"symbol": {}, "note": {}}}}},
        "paths": {
            "/watches": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/NewWatch"}
                            }
                        }
                    }
                }
            }
        },
    }
    assert "required" not in require_response_fields(schema)["components"]["schemas"]["NewWatch"]


def test_a_model_reached_only_through_another_request_model_keeps_it_too() -> None:
    """The transitive half, which the loop exists for: a body's model holding another one."""
    schema = {
        "components": {
            "schemas": {
                "NewWatch": {"properties": {"rule": {"$ref": "#/components/schemas/Rule"}}},
                "Rule": {"properties": {"kind": {}, "window": {}}},
            }
        },
        "paths": {
            "/watches": {
                "post": {"requestBody": {"schema": {"$ref": "#/components/schemas/NewWatch"}}}
            }
        },
    }
    assert "required" not in require_response_fields(schema)["components"]["schemas"]["Rule"]


def test_it_is_idempotent() -> None:
    """FastAPI hands back the same cached object every time, so a second pass over an augmented
    document must leave it alone."""
    once = require_response_fields(document_with({"Candle": {"properties": {"close": {}}}}))
    assert require_response_fields(once) == once
