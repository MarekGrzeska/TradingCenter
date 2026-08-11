from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent.app import app

# The lifespan now opens a real pool — it did not, back when this file's tests were
# first written, and their env carried a DATABASE_URL nothing was listening on. A `db`
# test since group 4 (`app.state.pool`, `POST /sessions` etc.), pointed at the
# throwaway container `migrated_url` gives.
pytestmark = pytest.mark.db

_ENV = {
    "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com",
    "AZURE_OPENAI_API_VERSION": "2026-01-01",
    "AZURE_OPENAI_API_KEY": "key",
    "MODELS": (
        '[{"id":"gpt-5.6-sol","deployment":"sol-prod","display_name":"Sol",'
        '"cost_rank":3,"input_rate_per_1k":"0.005","output_rate_per_1k":"0.03"},'
        '{"id":"gpt-5.6-luna","deployment":"luna-prod","display_name":"Luna",'
        '"cost_rank":1,"input_rate_per_1k":"0.001","output_rate_per_1k":"0.006"}]'
    ),
    "DEFAULT_MODEL_ID": "gpt-5.6-luna",
}


@pytest.fixture(autouse=True)
def _env(migrated_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", migrated_url)
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_models_is_enough_to_build_a_wybierak() -> None:
    # specs/agent-models, "Terminal buduje wybierak" — id, display name, cost order and
    # rates, cheapest first, with nothing beyond that a caller has to already know.
    with TestClient(app) as client:
        response = client.get("/models")
    assert response.status_code == 200
    body = response.json()
    assert [m["id"] for m in body] == ["gpt-5.6-luna", "gpt-5.6-sol"]
    assert body[0]["display_name"] == "Luna"
    assert body[0]["input_rate_per_1k"] == "0.001"
    assert "deployment" not in body[0]
