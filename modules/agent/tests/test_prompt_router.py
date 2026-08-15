from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent.app import app

pytestmark = pytest.mark.db

_ENV = {
    "OPENAI_API_KEY": "key",
    "MODELS": (
        '[{"id":"gpt-5.6-luna","model":"luna-prod","display_name":"Luna",'
        '"cost_rank":1,"input_rate_per_1m":"1","output_rate_per_1m":"6"}]'
    ),
    "DEFAULT_MODEL_ID": "gpt-5.6-luna",
}


@pytest.fixture(autouse=True)
def _env(migrated_url: str, db, monkeypatch: pytest.MonkeyPatch) -> None:
    del db  # requested for its TRUNCATE side effect — see test_usage_router.py's twin
    monkeypatch.setenv("DATABASE_URL", migrated_url)
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)


def test_get_prompt_reads_the_seeded_revision() -> None:
    with TestClient(app) as client:
        response = client.get("/prompt")

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == "v4"
    assert body["with_tools"] != body["without_tools"]


def test_put_prompt_creates_a_new_version_and_get_reflects_it() -> None:
    with TestClient(app) as client:
        put_response = client.put(
            "/prompt", json={"with_tools": "new with tools", "without_tools": "new without"}
        )
        get_response = client.get("/prompt")

    assert put_response.status_code == 200
    assert put_response.json()["version"] == "v5"
    assert put_response.json()["with_tools"] == "new with tools"
    assert get_response.json() == put_response.json()


def test_put_prompt_refuses_a_blank_variant() -> None:
    with TestClient(app) as client:
        response = client.put("/prompt", json={"with_tools": "   ", "without_tools": "fine"})
        unchanged = client.get("/prompt")

    assert response.status_code == 422
    assert unchanged.json()["version"] == "v4"


def test_prompt_routes_refuse_an_unauthenticated_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REQUIRE_AUTHENTICATED_PRINCIPAL", "true")
    with TestClient(app) as client:
        get_response = client.get("/prompt")
        put_response = client.put(
            "/prompt", json={"with_tools": "a", "without_tools": "b"}
        )

    assert get_response.status_code == 401
    assert put_response.status_code == 401
