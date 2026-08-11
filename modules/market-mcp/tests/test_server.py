from __future__ import annotations

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
