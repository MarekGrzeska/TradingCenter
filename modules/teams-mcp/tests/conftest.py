from __future__ import annotations

import pytest

from teams_mcp.client import TeamsClient
from teams_mcp.config import Settings
from teams_mcp.server import build_server

BASE = "http://127.0.0.1:8050"
# The deployed upstream, used by the fixtures that stand on the other side of
# `Settings.operator_identity_optional`. A hostname, not a real deployment's secret.
REMOTE = "https://app-tradingcenter-teams.azurewebsites.net"
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
    """The local shape, and that is load-bearing rather than incidental: loopback `teams`
    with no authenticator in front is exactly where `operator_identity_optional` is true
    (`config.py`). Tests that want the other side of that boundary take `guarded_settings`."""
    return Settings(teams_url=BASE, _env_file=None)  # type: ignore[call-arg]


@pytest.fixture
def guarded_settings() -> Settings:
    """The deployed shape: an authenticator in front and a `teams` off this machine, so a
    missing operator identity is a broken chain and not a desk."""
    return Settings(  # type: ignore[call-arg]
        teams_url=REMOTE,
        teams_scope="api://tradingcenter-teams/.default",
        require_authenticated_principal=True,
        _env_file=None,
    )


@pytest.fixture
def teams(settings: Settings) -> TeamsClient:
    return TeamsClient(settings)


@pytest.fixture
def guarded_server(guarded_settings: Settings):
    """A server built on the deployed shape, for the tests that check what happens when
    nobody is behind a call there. Deliberately not paired with `signed_in`."""
    client = TeamsClient(guarded_settings)
    return build_server(guarded_settings, client), client


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
        # `optional` is accepted and ignored: a signed-in operator's token is the same
        # token whether or not an absent one would have been tolerated.
        "teams_mcp.tools._shared.operator_token",
        lambda _context, optional=False: OPERATOR_TOKEN,
    )
    return OPERATOR_TOKEN
