from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent.app import app

# The lifespan builds a real Settings() from the environment — these are the minimum a
# started process needs, mirroring tests/test_config.py's REQUIRED.
_ENV = {
    "DATABASE_URL": "postgresql://agent:change-me@127.0.0.1:55432/agent",
    "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com",
    "AZURE_OPENAI_API_VERSION": "2026-01-01",
    "AZURE_OPENAI_API_KEY": "key",
    "MODELS": (
        '[{"id":"gpt-5.6-luna","deployment":"luna-prod","display_name":"Luna",'
        '"cost_rank":1,"input_rate_per_1k":"0.001","output_rate_per_1k":"0.006"}]'
    ),
    "DEFAULT_MODEL_ID": "gpt-5.6-luna",
}


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
