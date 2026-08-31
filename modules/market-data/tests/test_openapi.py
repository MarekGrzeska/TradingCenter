"""The published contract the terminal's generated types are built from. Not tests of FastAPI: they pin
what the generator depends on, including the subscription's messages FastAPI does not describe."""

from __future__ import annotations

import json

import httpx
import pytest

from market_data.openapi import document

# Every shape the terminal reads off the wire. Named rather than counted: adding a model is ordinary,
# while losing one silently breaks a generated type and, a step later, a screen.
CONSUMED_BY_THE_TERMINAL = {
    "CandleOut",
    "CandlesOut",
    "CoverageOut",
    "PairCoverageOut",
    "TrackedPairOut",
    "TrackedPairResult",
    "TrackPairsResult",
    "PairDeletionOut",
    "ChunkOut",
    "JobOut",
    "JobPairViewOut",
    "PairEstimateOut",
    "JobEstimateOut",
    "Problem",
    # The subscription's messages, which have no path and would otherwise be absent.
    "Snapshot",
    "CandleChange",
    "Candle",
}


def test_the_document_describes_every_shape_the_terminal_reads() -> None:
    schemas = document()["components"]["schemas"]

    assert CONSUMED_BY_THE_TERMINAL <= set(schemas)


def test_the_subscription_messages_are_published_although_it_has_no_path() -> None:
    schema = document()

    # The route genuinely is not there — OpenAPI has no place for a WebSocket — so its
    # absence is the thing that makes the components below necessary rather than a bug.
    assert "/ws/candles" not in schema["paths"]

    schemas = schema["components"]["schemas"]
    assert schemas["Snapshot"]["properties"]["candles"]["items"] == {
        "$ref": "#/components/schemas/Candle"
    }
    assert schemas["CandleChange"]["properties"]["candle"] == {
        "$ref": "#/components/schemas/Candle"
    }


def test_a_response_model_declares_every_field_it_always_sends() -> None:
    """A field with a default is not `required` to Pydantic, but this module answers with it regardless.
    A consumer generating types off the raw reading gets `T | undefined` for a case that cannot happen."""
    schemas = document()["components"]["schemas"]

    tracked = schemas["TrackedPairOut"]
    assert "earliest_candle" in tracked["properties"]
    assert sorted(tracked["required"]) == sorted(tracked["properties"])


def test_a_request_model_keeps_its_optional_fields_optional() -> None:
    """The other half, and the reason this is not a blanket rule: omitting a field a
    caller *sends* is how a default gets used."""
    schemas = document()["components"]["schemas"]

    request = schemas["TrackPairRequest"]
    assert request.get("required", []) != sorted(request["properties"])


def test_a_model_reached_only_through_a_request_body_counts_as_a_request() -> None:
    # `PairRequest` is nested inside `TrackPairRequest`, never returned alone. The request side is found
    # by reachability rather than a list of names, so a model that moves sides is not left behind.
    schemas = document()["components"]["schemas"]

    nested = schemas["PairRequest"]
    assert sorted(nested.get("required", [])) != sorted(nested["properties"])


def test_augmenting_twice_changes_nothing() -> None:
    # FastAPI caches its document on the app and hands back the same object, so the
    # augmentation runs again on every call after the first.
    once = json.dumps(document(), sort_keys=True)
    twice = json.dumps(document(), sort_keys=True)

    assert once == twice


# Served through the app rather than read from `document()`, because what these pin is what a consumer
# actually fetches. `/openapi.json` reads no state, so they lost their PostgreSQL container on the way.


@pytest.fixture
async def served(app, settings):
    app.state.settings = settings
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://archive.test") as client:
        yield client


async def test_the_websocket_path_is_absent_from_the_schema(served) -> None:
    """OpenAPI has no vocabulary for WebSocket payloads, so a path appearing there would describe a
    contract it cannot state — and the README would become a second description."""
    schema = (await served.get("/openapi.json")).json()

    assert "/ws/candles" not in schema["paths"]
    assert not [path for path in schema["paths"] if path.startswith("/ws")]


async def test_the_http_routes_are_all_described(served) -> None:
    paths = (await served.get("/openapi.json")).json()["paths"]

    assert {
        "/candles/{symbol}",
        "/coverage/{symbol}",
        "/pairs",
        "/pairs/{symbol}",
        "/deletions",
        "/jobs/estimate",
        "/jobs",
        "/jobs/{job_id}",
        "/jobs/{job_id}/retry",
    } <= set(paths)


async def test_the_schema_says_which_side_of_the_spread_is_stored(served) -> None:
    schema = (await served.get("/openapi.json")).json()

    assert "bid" in schema["info"]["description"]
