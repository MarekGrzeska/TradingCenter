from __future__ import annotations

import httpx
import respx
from starlette.testclient import TestClient

from market_mcp.client import UpstreamClient
from market_mcp.config import Settings
from market_mcp.server import build_server


def test_health_answers_without_an_mcp_session(settings: Settings) -> None:
    upstream = UpstreamClient(settings)
    mcp = build_server(settings, upstream)
    app = mcp.streamable_http_app()

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@respx.mock
def test_health_answers_even_when_the_archive_is_unreachable(settings: Settings) -> None:
    """Task 5.3: `/health` never calls market-data — a dead archive and a dead
    module MUST NOT look the same to the platform deciding whether to restart the
    container (specs/market-mcp-transport, "Sonda przy niedostępnym archiwum")."""
    respx.get("http://127.0.0.1:8020/pairs").mock(side_effect=httpx.ConnectError("refused"))

    upstream = UpstreamClient(settings)
    mcp = build_server(settings, upstream)
    app = mcp.streamable_http_app()

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
