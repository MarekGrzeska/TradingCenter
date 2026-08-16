"""specs/teams-mcp-transport — one transport, one named caller, one unauthenticated way
in that says nothing about the catalogue. A twin of market-mcp's and trading-mcp's tests
of the same middleware, on a module whose tools create teams in somebody's name."""

from __future__ import annotations

import inspect
import logging

from starlette.testclient import TestClient

from teams_mcp import __main__ as entrypoint
from teams_mcp.client import TeamsClient
from teams_mcp.config import Settings
from teams_mcp.server import build_http_app


def _client(require: bool) -> TestClient:
    settings = Settings(
        teams_url="http://127.0.0.1:8050",
        require_authenticated_principal=require,
        _env_file=None,  # type: ignore[call-arg]
    )
    return TestClient(build_http_app(settings, TeamsClient(settings)))


def test_the_entrypoint_takes_no_transport_argument() -> None:
    assert not inspect.signature(entrypoint.main).parameters


def test_the_entrypoint_never_runs_the_stdio_transport() -> None:
    source = inspect.getsource(entrypoint)
    assert "run_stdio_async" not in source
    assert "argparse" not in source


def test_health_needs_no_identity_even_when_required() -> None:
    with _client(require=True) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_reveals_nothing_about_the_catalogue() -> None:
    with _client(require=False) as client:
        body = client.get("/health").text
    for leaked in ("team", "owner", "operator", "principal"):
        assert leaked not in body.lower()


def test_request_without_identity_is_refused_when_required() -> None:
    with _client(require=True) as client:
        response = client.post("/mcp", json={"jsonrpc": "2.0", "method": "ping", "id": 1})
    assert response.status_code == 401


def test_request_with_identity_is_not_refused_by_this_layer(caplog) -> None:
    with (
        caplog.at_level(logging.INFO, logger="teams_mcp.network_identity"),
        _client(require=True) as client,
    ):
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "ping", "id": 1},
            headers={"X-MS-CLIENT-PRINCIPAL-ID": "agent-managed-identity"},
        )
    assert response.status_code != 401
    assert any("agent-managed-identity" in record.message for record in caplog.records)


def test_request_without_identity_is_let_through_when_not_required(caplog) -> None:
    with (
        caplog.at_level(logging.INFO, logger="teams_mcp.network_identity"),
        _client(require=False) as client,
    ):
        response = client.post("/mcp", json={"jsonrpc": "2.0", "method": "ping", "id": 1})
    assert response.status_code != 401
    assert any("anonymous" in record.message for record in caplog.records)


def test_the_identity_wrapper_is_raw_asgi_not_a_buffering_middleware() -> None:
    # BaseHTTPMiddleware buffers a response body in some Starlette versions, which
    # would break the streaming transport it wraps.
    from teams_mcp.network_identity import RequireCallerIdentity

    assert "BaseHTTPMiddleware" not in inspect.getsource(RequireCallerIdentity)
