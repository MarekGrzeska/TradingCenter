"""Every field this module reads off capital-gateway's wire, checked against the committed snapshot
rather than assumed. No running gateway needed: the snapshot is a file."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

SNAPSHOT = Path(__file__).resolve().parent.parent / "contract" / "capital-gateway.openapi.json"


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def _response_schema(schema: dict, path: str, model: str) -> dict:
    ref = schema["paths"][path]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ]
    name = ref.get("$ref", "").rsplit("/", 1)[-1] or model
    return schema["components"]["schemas"][name]


def test_capabilities_carries_environment(schema: dict) -> None:
    """`ensure_demo_environment()`'s whole check reads one field off this response —
    if the gateway ever stops publishing it, this must fail before that guard does."""
    model = _response_schema(schema, "/capabilities", "Capabilities")
    assert "environment" in model["properties"]


def test_trading_routes_are_still_published(schema: dict) -> None:
    """The routes group 3's tools call. Not their shapes yet — just that the routes this module is
    built around have not moved."""
    paths = schema["paths"]
    assert "/positions" in paths
    assert "/orders" in paths
    assert "/positions/{position_id}" in paths
    assert "/working-orders" in paths
    assert "/working-orders/{order_id}" in paths
