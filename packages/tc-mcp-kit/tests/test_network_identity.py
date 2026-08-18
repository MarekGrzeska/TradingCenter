"""One copy of what `market-mcp`, `teams-mcp` and `trading-mcp` each carried before
18 August 2026. Was tested only indirectly, through each module's own HTTP app — this is
the first place the middleware itself is tested, independent of any of the three servers.
"""

from __future__ import annotations

import inspect
import logging

from starlette.testclient import TestClient
from starlette.types import Receive, Scope, Send

from tc_mcp_kit.network_identity import RequireCallerIdentity


async def _reached(scope: Scope, receive: Receive, send: Send) -> None:
    del receive
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"reached"})


def _client(require: bool) -> TestClient:
    # No `with`: `_reached` answers HTTP only and does not speak the lifespan
    # protocol TestClient's context manager waits on — every module's real app does,
    # through FastAPI, but that is not what this test is exercising.
    return TestClient(RequireCallerIdentity(_reached, require_authenticated_principal=require))


def test_health_needs_no_identity_even_when_required() -> None:
    response = _client(require=True).get("/health")
    assert response.status_code == 200


def test_request_without_identity_is_refused_when_required() -> None:
    response = _client(require=True).post("/mcp")
    assert response.status_code == 401


def test_request_with_identity_is_not_refused_and_is_logged(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="tc_mcp_kit.network_identity"):
        response = _client(require=True).post(
            "/mcp", headers={"X-MS-CLIENT-PRINCIPAL-ID": "principal-123"}
        )
    assert response.status_code == 200
    assert any("principal-123" in record.message for record in caplog.records)


def test_request_without_identity_is_let_through_when_not_required(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="tc_mcp_kit.network_identity"):
        response = _client(require=False).post("/mcp")
    assert response.status_code == 200
    assert any("anonymous" in record.message for record in caplog.records)


def test_refusal_is_logged_without_leaking_the_request_body(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="tc_mcp_kit.network_identity"):
        _client(require=True).post(
            "/mcp", json={"jsonrpc": "2.0", "method": "secret-method", "id": 1}
        )

    joined = "\n".join(record.message for record in caplog.records)
    assert "refused" in joined
    assert "secret-method" not in joined


def test_the_wrapper_is_raw_asgi_not_a_buffering_middleware() -> None:
    # BaseHTTPMiddleware buffers a response body in some Starlette versions, which
    # would break the streaming transport (streamable-http) it wraps.
    assert "BaseHTTPMiddleware" not in inspect.getsource(RequireCallerIdentity)
