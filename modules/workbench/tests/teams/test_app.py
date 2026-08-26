from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from tc_runtime import schema_version
from tc_runtime.schema_version import SchemaMismatch

from workbench.app import app

from .mcp_stand_in import free_port

# The lifespan opens a real pool, migrates and checks the schema — needs the throwaway
# container `migrated_url` gives.
pytestmark = pytest.mark.db

_ENV = {
    "TEAMS_OPENAI_API_KEY": "key",
    "TEAMS_MODELS": (
        '[{"id":"gpt-5.6-luna","model":"luna-prod","display_name":"Luna",'
        '"cost_rank":1,"input_rate_per_1m":"1","output_rate_per_1m":"6"}]'
    ),
}


@pytest.fixture(autouse=True)
def _env(workbench_env: None, migrated_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)


def test_the_module_starts_with_no_tool_server_configured() -> None:
    """"Moduł startuje bez serwera narzędzi": no tool-server URL is set, so this is the state a fresh
    deployment is in before the operator's apply — a supported state, not a broken one."""
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        # `remote()`, not `configured()`: the registry always holds the sources this process serves
        # itself, and "no tool server" is a claim about the ones with an address.
        assert app.state.teams.tools.remote() == []


def test_a_tool_server_that_is_not_answering_does_not_stop_the_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Nothing listens on this port. The session is opened lazily, so start-up never learns
    # that — which is the whole point: a run needing tools is refused, a module is not.
    monkeypatch.setenv("MARKET_MCP_URL", f"http://127.0.0.1:{free_port()}")

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert [server.label for server in app.state.teams.tools.remote()] == ["market-mcp"]


def test_a_schema_the_image_was_not_built_for_refuses_to_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The wiring, not the comparison — `test_schema_version.py` owns the comparison.
    # What this proves is that a mismatch reaches the lifespan and stops it.
    monkeypatch.setattr(schema_version, "expected_heads", lambda _migrations: {"9999_from_a_newer_image"})

    with pytest.raises(SchemaMismatch), TestClient(app):
        pass  # pragma: no cover - the lifespan raises before the body runs
