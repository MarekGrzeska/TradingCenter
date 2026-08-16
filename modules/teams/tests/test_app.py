from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from teams import schema_version
from teams.app import app
from teams.schema_version import SchemaMismatch

# The lifespan opens a real pool, migrates and checks the schema — needs the throwaway
# container `migrated_url` gives.
pytestmark = pytest.mark.db

_ENV = {
    "OPENAI_API_KEY": "key",
    "MODELS": (
        '[{"id":"gpt-5.6-luna","model":"luna-prod","display_name":"Luna",'
        '"cost_rank":1,"input_rate_per_1m":"1","output_rate_per_1m":"6"}]'
    ),
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


def test_health_requires_no_identity() -> None:
    # No REQUIRE_AUTHENTICATED_PRINCIPAL set — off by default — and no principal header
    # sent; the route MUST NOT depend on `current_principal`.
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200


def test_a_schema_the_image_was_not_built_for_refuses_to_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The wiring, not the comparison — `test_schema_version.py` owns the comparison.
    # What this proves is that a mismatch reaches the lifespan and stops it.
    monkeypatch.setattr(schema_version, "expected_heads", lambda: {"9999_from_a_newer_image"})

    with pytest.raises(SchemaMismatch), TestClient(app):
        pass  # pragma: no cover - the lifespan raises before the body runs
