from __future__ import annotations

import pytest

from teams_mcp.client import TeamsClient
from teams_mcp.config import Settings
from teams_mcp.server import build_server

BASE = "http://127.0.0.1:8050"
# Not a real token and not shaped like one on purpose: nothing here parses it, and a
# test carrying something that looks like a credential invites somebody to paste a real
# one in its place.
OPERATOR_TOKEN = "operator-token-for-tests"


@pytest.fixture(autouse=True)
def _no_ambient_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep a developer's real .env out of the tests — `Settings` reads the environment
    and the .env file, so without this a machine holding one runs different tests than
    a machine without it."""
    for name in (
        "TEAMS_URL",
        "TEAMS_SCOPE",
        "TEAMS_REQUEST_TIMEOUT_SECONDS",
        "TEAMS_MCP_PORT",
        "TEAMS_MCP_HOST",
        "REQUIRE_AUTHENTICATED_PRINCIPAL",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def settings() -> Settings:
    return Settings(teams_url=BASE, _env_file=None)  # type: ignore[call-arg]


@pytest.fixture
def teams(settings: Settings) -> TeamsClient:
    return TeamsClient(settings)


@pytest.fixture
def server(settings: Settings, teams: TeamsClient):
    """The server and the client it was built with, so a test can mock the exact base
    URL it will call — same shape as both other MCP modules' own `server` fixture."""
    return build_server(settings, teams), teams


@pytest.fixture
def signed_in(monkeypatch: pytest.MonkeyPatch):
    """Every tool asks `operator.operator_token` for the caller's credential before it
    touches the network. Calling a tool through `mcp.call_tool` has no HTTP request
    behind it, so the token is supplied here — the extraction itself is what
    `test_operator.py` checks, and stubbing it there would leave nothing tested."""
    monkeypatch.setattr(
        "teams_mcp.tools._shared.operator_token", lambda _context: OPERATOR_TOKEN
    )
    return OPERATOR_TOKEN
