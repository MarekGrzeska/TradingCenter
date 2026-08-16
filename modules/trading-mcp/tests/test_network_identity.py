"""The network transport's caller-identity requirement — a twin of market-mcp's own
test of the same middleware."""

from __future__ import annotations

import logging

from starlette.testclient import TestClient

from trading_mcp.client import GatewayClient
from trading_mcp.config import Settings
from trading_mcp.server import build_http_app


def _client(require: bool) -> TestClient:
    settings = Settings(
        capital_gateway_url="http://127.0.0.1:8010",
        capital_gateway_api_key="test-gateway-key",
        require_authenticated_principal=require,
        _env_file=None,  # type: ignore[call-arg]
    )
    gateway = GatewayClient(settings)
    app = build_http_app(settings, gateway)
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
        caplog.at_level(logging.INFO, logger="trading_mcp.network_identity"),
        _client(require=True) as client,
    ):
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "ping", "id": 1},
            headers={"X-MS-CLIENT-PRINCIPAL-ID": "principal-123"},
        )
    assert response.status_code != 401
    assert any("principal-123" in record.message for record in caplog.records)


def test_request_without_identity_is_let_through_when_not_required(caplog) -> None:
    with (
        caplog.at_level(logging.INFO, logger="trading_mcp.network_identity"),
        _client(require=False) as client,
    ):
        response = client.post("/mcp", json={"jsonrpc": "2.0", "method": "ping", "id": 1})
    assert response.status_code != 401
    assert any("anonymous" in record.message for record in caplog.records)


def test_health_reveals_nothing_about_the_account() -> None:
    with _client(require=False) as client:
        response = client.get("/health")
    assert response.json() == {"status": "ok"}
