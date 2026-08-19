"""The published contract, and the fact that it can be read without running anything.

These are not tests of FastAPI. They pin the two properties the terminal's generated
types depend on: the document is obtainable from the code alone, and it describes the
subscription's messages, which FastAPI by itself does not.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from market_data.openapi import document

# Every shape the terminal reads off the wire. Named rather than counted: adding a model
# is ordinary and must not fail this, while losing one of these silently breaks a
# generated type and, a step later, a screen.
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
    """A field with a default is not `required` to Pydantic, but this module answers with
    it regardless — `null` when there is none. A consumer generating types off the raw
    reading gets `T | undefined` for a case that cannot happen."""
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
    # `PairRequest` is nested inside `TrackPairRequest`, never returned on its own. The
    # request side is found by reachability rather than by a list of names, so a model
    # that moves sides cannot be left behind by a list nobody updated.
    schemas = document()["components"]["schemas"]

    nested = schemas["PairRequest"]
    assert sorted(nested.get("required", [])) != sorted(nested["properties"])


def test_augmenting_twice_changes_nothing() -> None:
    # FastAPI caches its document on the app and hands back the same object, so the
    # augmentation runs again on every call after the first.
    once = json.dumps(document(), sort_keys=True)
    twice = json.dumps(document(), sort_keys=True)

    assert once == twice


def test_the_document_prints_with_no_environment_at_all() -> None:
    """No database, no gateway, no settings — the property the generator relies on.

    Run as a subprocess with a stripped environment rather than by calling `main()`:
    importing this module has already imported the app, so an in-process check could
    not tell whether the import itself needs anything.
    """
    root = Path(__file__).resolve().parents[1]

    # `SystemRoot` is carried on Windows and is not one of the variables under test:
    # winsock resolves its provider catalogue through the registry, so `_overlapped`
    # — which importing the app pulls in with asyncio's proactor loop — dies with
    # WinError 10106 without it. What the test asserts is that no CAPITAL_*,
    # DATABASE_* or AZURE_* setting is needed, and none is carried.
    env = {"PATH": "/usr/bin:/bin"}
    if sys.platform == "win32":
        env["SystemRoot"] = os.environ["SystemRoot"]

    finished = subprocess.run(
        [sys.executable, "-m", "market_data.openapi"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert finished.returncode == 0, finished.stderr
    assert CONSUMED_BY_THE_TERMINAL <= set(json.loads(finished.stdout)["components"]["schemas"])


def test_the_printed_bytes_are_stable() -> None:
    """The generated TypeScript is committed and compared, so an unordered dump would
    produce diffs nobody can act on."""
    root = Path(__file__).resolve().parents[1]
    runs = [
        subprocess.run(
            [sys.executable, "-m", "market_data.openapi"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        for _ in range(2)
    ]

    assert runs[0] == runs[1]


# --- 8.8: the schema describes the HTTP contract and nothing else ---------------------
#
# Served through the app rather than read from `document()`, because what these three
# pin is what a consumer actually fetches. They arrived here from `test_app.py` and lost
# their PostgreSQL container on the way: `/openapi.json` is built from the routes and
# reads no state, so `api` — which brings a database with it — was never what they needed.


@pytest.fixture
async def served(app, settings):
    app.state.settings = settings
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://archive.test") as client:
        yield client


async def test_the_websocket_path_is_absent_from_the_schema(served) -> None:
    """OpenAPI has no vocabulary for WebSocket payloads, so a path that appeared there
    would describe a contract it cannot actually state — and the README would become the
    second description rather than the only one."""
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
