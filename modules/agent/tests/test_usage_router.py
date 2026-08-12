from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from agent.app import app
from agent.provider import TextDelta, UsageReport

pytestmark = pytest.mark.db

_ENV = {
    "OPENAI_API_KEY": "key",
    "MODELS": (
        '[{"id":"gpt-5.6-luna","model":"luna-prod","display_name":"Luna",'
        '"cost_rank":1,"input_rate_per_1k":"0.001","output_rate_per_1k":"0.006"}]'
    ),
    "DEFAULT_MODEL_ID": "gpt-5.6-luna",
}


@pytest.fixture(autouse=True)
def _env(migrated_url: str, db, monkeypatch: pytest.MonkeyPatch) -> None:
    # `db` is requested for its side effect, not its value: TestClient below opens its
    # own pool against the same `migrated_url`, and without `db`'s TRUNCATE this file
    # shares one un-reset database across every test in the session — invisible to a
    # test that only checks its own session id, but not to one asserting an empty
    # summary against everyone else who wrote to it first.
    del db
    monkeypatch.setenv("DATABASE_URL", migrated_url)
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)


class _FakeProvider:
    def __init__(self, chunks: list) -> None:
        self._chunks = chunks

    async def stream(self, *, model: str, system_prompt: str, history: list):
        for chunk in self._chunks:
            yield chunk


def test_usage_reflects_a_completed_turn() -> None:
    with TestClient(app) as client:
        app.state.provider = _FakeProvider(
            [TextDelta("hi"), UsageReport(1000, 500, None, None)]
        )
        session_id = client.post("/sessions", json={}).json()["id"]
        client.post(f"/sessions/{session_id}/messages", json={"content": "hello"})
        response = client.get("/usage")

    assert response.status_code == 200
    body = response.json()
    # 1000 input tokens @ 0.001/1k + 500 output tokens @ 0.006/1k = 0.001 + 0.003
    assert Decimal(body["total_cost"]) == Decimal("0.001") + Decimal("0.003")
    assert body["by_model"][0]["key"] == "gpt-5.6-luna"
    assert body["by_session"][0]["key"] == str(session_id)
    assert len(body["by_day"]) == 1


def test_usage_with_no_activity_is_an_empty_summary_not_an_error() -> None:
    with TestClient(app) as client:
        response = client.get("/usage")
    assert response.status_code == 200
    body = response.json()
    assert Decimal(body["total_cost"]) == 0
    assert body["by_model"] == []
    assert body["by_session"] == []
    assert body["by_day"] == []
