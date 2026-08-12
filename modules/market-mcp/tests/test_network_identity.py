"""Task 5.2: the network transport's caller-identity requirement."""

from __future__ import annotations

import logging

from starlette.testclient import TestClient

from market_mcp.client import UpstreamClient
from market_mcp.config import Settings
from market_mcp.server import build_http_app


def _client(require: bool) -> TestClient:
    settings = Settings(
        market_data_url="http://127.0.0.1:8020",
        require_authenticated_principal=require,
        _env_file=None,  # type: ignore[call-arg]
    )
    upstream = UpstreamClient(settings)
    app = build_http_app(settings, upstream)
    return TestClient(app)


def test_health_needs_no_identity_even_when_required() -> None:
    with _client(require=True) as client:
        response = client.get("/health")
    assert response.status_code == 200


def test_request_without_identity_is_refused_when_required() -> None:
    with _client(require=True) as client:
        response = client.post("/mcp", json={"jsonrpc": "2.0", "method": "ping", "id": 1})
    assert response.status_code == 401


def test_request_with_identity_is_not_refused_by_this_layer(caplog) -> None:
    with (
        caplog.at_level(logging.INFO, logger="market_mcp.network_identity"),
        _client(require=True) as client,
    ):
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "ping", "id": 1},
            headers={"X-MS-CLIENT-PRINCIPAL-ID": "principal-123"},
        )
    # Not 401 from this middleware — whatever status the MCP route itself answers
    # with is a separate concern from whether the identity check let the request
    # through, which it must have for the code to reach that far.
    assert response.status_code != 401
    assert any("principal-123" in record.message for record in caplog.records)


def test_request_without_identity_is_let_through_when_not_required(caplog) -> None:
    with (
        caplog.at_level(logging.INFO, logger="market_mcp.network_identity"),
        _client(require=False) as client,
    ):
        response = client.post("/mcp", json={"jsonrpc": "2.0", "method": "ping", "id": 1})
    assert response.status_code != 401
    assert any("anonymous" in record.message for record in caplog.records)


def test_refusal_is_logged_without_leaking_the_request_body(caplog) -> None:
    with (
        caplog.at_level(logging.INFO, logger="market_mcp.network_identity"),
        _client(require=True) as client,
    ):
        client.post("/mcp", json={"jsonrpc": "2.0", "method": "secret-method", "id": 1})

    joined = "\n".join(record.message for record in caplog.records)
    assert "refused" in joined
    assert "secret-method" not in joined
