"""One copy of what all three MCP modules' `client.py` carried before 18 August 2026, tested here as
itself rather than indirectly through each module's own upstream client."""

from __future__ import annotations

import httpx

from tc_mcp_kit.detail import detail


def _response(status_code: int, *, json: object = None, text: str = "") -> httpx.Response:
    if json is not None:
        return httpx.Response(status_code, json=json)
    return httpx.Response(status_code, text=text)


def test_a_string_detail_travels_unchanged() -> None:
    response = _response(404, json={"detail": "position not found"})
    assert detail(response, upstream="capital-gateway") == "position not found"


def test_a_validation_list_is_flattened_to_one_sentence() -> None:
    response = _response(
        422,
        json={
            "detail": [
                {"loc": ["body", "epic"], "msg": "Field required"},
                {"loc": ["query", "size"], "msg": "must be positive"},
            ]
        },
    )
    assert detail(response, upstream="trading-mcp") == "epic: Field required; size: must be positive"


def test_a_validation_entry_drops_fastapis_own_plumbing_from_loc() -> None:
    response = _response(422, json={"detail": [{"loc": ["body"], "msg": "Field required"}]})
    # `loc` with only plumbing segments (`body`, `query`, `path`) names no field.
    assert detail(response, upstream="teams-mcp") == "Field required"


def test_a_non_json_body_falls_back_to_the_response_text() -> None:
    response = _response(500, text="upstream is down")
    assert detail(response, upstream="market-mcp") == "upstream is down"


def test_a_json_body_that_is_not_an_object_does_not_raise() -> None:
    # A bad query parameter used to reach a model as the repr of a list of dicts —
    # `.get` on a list raises `AttributeError`, which `except ValueError` does not catch.
    response = _response(422, json=[{"loc": ["query", "epic"], "msg": "Field required"}])
    assert "Field required" in detail(response, upstream="market-mcp")
