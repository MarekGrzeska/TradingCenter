from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent import schema_version
from agent.app import app
from agent.schema_version import SchemaMismatch

# The lifespan now opens a real pool — it did not, back when this file's tests were
# first written, and their env carried a DATABASE_URL nothing was listening on. A `db`
# test since group 4 (`app.state.pool`, `POST /sessions` etc.), pointed at the
# throwaway container `migrated_url` gives.
pytestmark = pytest.mark.db

_ENV = {
    "OPENAI_API_KEY": "key",
    "MODELS": (
        '[{"id":"gpt-5.6-sol","model":"sol-prod","display_name":"Sol",'
        '"cost_rank":3,"input_rate_per_1m":"5","output_rate_per_1m":"30"},'
        '{"id":"gpt-5.6-luna","model":"luna-prod","display_name":"Luna",'
        '"cost_rank":1,"input_rate_per_1m":"1","output_rate_per_1m":"6"}]'
    ),
    "DEFAULT_MODEL_ID": "gpt-5.6-luna",
}


@pytest.fixture(autouse=True)
def _env(migrated_url: str, db, monkeypatch: pytest.MonkeyPatch) -> None:
    # `db` requested for its TRUNCATE side effect — see test_usage_router.py's twin.
    del db
    monkeypatch.setenv("DATABASE_URL", migrated_url)
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_a_schema_the_image_was_not_built_for_refuses_to_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The wiring, not the comparison — `test_schema_version.py` owns the comparison. What
    # this proves is that a mismatch reaches the lifespan and stops it, which is the whole
    # value: the check ran on 15 August's production database too, in the sense that
    # nothing called it.
    monkeypatch.setattr(schema_version, "expected_heads", lambda: {"9999_from_a_newer_image"})

    with pytest.raises(SchemaMismatch), TestClient(app):
        pass  # pragma: no cover - the lifespan raises before the body runs


def test_get_models_is_enough_to_build_a_wybierak() -> None:
    # specs/agent-models, "Terminal buduje wybierak" — id, display name, cost order and
    # rates, cheapest first, with nothing beyond that a caller has to already know.
    with TestClient(app) as client:
        response = client.get("/models")
    assert response.status_code == 200
    body = response.json()
    assert [m["id"] for m in body] == ["gpt-5.6-luna", "gpt-5.6-sol"]
    assert body[0]["display_name"] == "Luna"
    assert body[0]["input_rate_per_1m"] == "1"
    assert "model" not in body[0]
