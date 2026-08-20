"""The settings rules both surfaces carry identically, checked once for both.

`agent.config.Settings` and `teams.config.Settings` are separate classes on purpose — the
prefixed names are what stays doubled (`AGENT_DATABASE_URL` against `TEAMS_DATABASE_URL`,
two keys, two catalogues). Two of their validator blocks are not doubled in any meaningful
sense: the database-mode rules and the market-mcp mode switch were a byte-identical block
in both suites apart from the word "agent" or "teams" inside a URL. A rule fixed on one
surface could rot on the other with nothing to say so.

Each surface's own `tests/*/test_config.py` keeps what is genuinely its own: its key, its
catalogue, and — for the conversation — its default model, for teams its second tool server.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError

from agent.config import Settings as AgentSettings
from teams.config import Settings as TeamsSettings

ONE_MODEL = [
    {
        "id": "gpt-5.6-luna",
        "model": "luna-prod",
        "display_name": "Luna",
        "cost_rank": 1,
        "input_rate_per_1m": "1",
        "output_rate_per_1m": "6",
    }
]

_REQUIRED: dict[str, dict[str, Any]] = {
    "agent": {
        "database_url": "postgresql://localhost:5432/agent?sslmode=require",
        "database_user": "agent",
        "openai_api_key": "key",
        "models": ONE_MODEL,
        "default_model_id": "gpt-5.6-luna",
    },
    "teams": {
        "database_url": "postgresql://localhost:5432/teams?sslmode=require",
        "database_user": "teams",
        "openai_api_key": "key",
        "models": ONE_MODEL,
    },
}

_CLASSES = {"agent": AgentSettings, "teams": TeamsSettings}


@pytest.fixture(params=["agent", "teams"])
def surface(request: pytest.FixtureRequest) -> str:
    return request.param


@pytest.fixture
def settings(surface: str) -> Callable[..., Any]:
    """A complete configuration for one surface, with the overrides a test names.

    `_env_file=None` so a developer's real .env cannot make a test pass or fail.
    """

    def build(**overrides: Any) -> Any:
        return _CLASSES[surface](**{**_REQUIRED[surface], **overrides}, _env_file=None)

    return build


def test_a_complete_configuration_builds(settings: Callable[..., Any]) -> None:
    assert settings().models[0].display_name == "Luna"


# --- database mode, same two failures as market-data/config.py ---


def test_no_database_user_with_a_loopback_url_is_local_mode(
    settings: Callable[..., Any], surface: str
) -> None:
    resolved = settings(
        database_user=None,
        database_url=f"postgresql://{surface}:change-me@127.0.0.1:55432/{surface}",
    )
    assert resolved.database_user is None


def test_a_blank_database_user_means_local_mode_not_a_role_named_blank(
    settings: Callable[..., Any], surface: str
) -> None:
    resolved = settings(
        database_user="   ",
        database_url=f"postgresql://{surface}:change-me@localhost:55432/{surface}",
    )
    assert resolved.database_user is None


def test_no_database_user_with_a_remote_host_refuses_to_start(
    settings: Callable[..., Any], surface: str
) -> None:
    with pytest.raises(ValidationError) as err:
        settings(
            database_user=None,
            database_url=(
                f"postgresql://{surface}:change-me@"
                f"psql-tradingcenter.postgres.database.azure.com/{surface}"
            ),
        )
    assert "DATABASE_USER" in str(err.value)
    assert "loopback" in str(err.value)


def test_a_database_url_that_does_not_require_tls_refuses_to_start(
    settings: Callable[..., Any], surface: str
) -> None:
    with pytest.raises(ValidationError) as err:
        settings(database_url=f"postgresql://localhost:5432/{surface}?sslmode=prefer")
    assert "TLS" in str(err.value)


def test_a_database_url_with_a_credential_refuses_to_start(
    settings: Callable[..., Any], surface: str
) -> None:
    with pytest.raises(ValidationError) as err:
        settings(database_url=f"postgresql://user:pass@localhost:5432/{surface}?sslmode=require")
    assert "DATABASE_URL" in str(err.value)


def test_local_mode_does_not_require_tls(settings: Callable[..., Any], surface: str) -> None:
    url = f"postgresql://{surface}:change-me@127.0.0.1:55432/{surface}"
    assert settings(database_user=None, database_url=url).database_url == url


def test_a_missing_database_url_names_itself(surface: str) -> None:
    with pytest.raises(ValidationError) as err:
        _CLASSES[surface](_env_file=None)  # pyright: ignore[reportCallIssue]
    assert "database_url" in str(err.value)


# --- the archive server's mode switch (specs/{agent,teams}-tool-access) ---


def test_no_tool_server_configured_is_a_valid_state(settings: Callable[..., Any]) -> None:
    # Not a misconfiguration: it is what the conversation was before it had tools, and for
    # teams it is what a team carrying no assigned tools never needs.
    assert settings().market_mcp_url is None


def test_remote_tool_server_without_a_scope_is_refused(settings: Callable[..., Any]) -> None:
    with pytest.raises(ValidationError) as err:
        settings(market_mcp_url="https://market-mcp.example.com")
    assert "MARKET_MCP_SCOPE" in str(err.value)


def test_scope_with_a_loopback_tool_server_is_refused(settings: Callable[..., Any]) -> None:
    with pytest.raises(ValidationError) as err:
        settings(market_mcp_url="http://127.0.0.1:8020", market_mcp_scope="api://some-app/.default")
    assert "loopback" in str(err.value)


def test_a_scope_with_no_url_at_all_is_refused(settings: Callable[..., Any]) -> None:
    with pytest.raises(ValidationError) as err:
        settings(market_mcp_scope="api://some-app/.default")
    assert "MARKET_MCP_URL" in str(err.value)


def test_loopback_tool_server_without_a_scope_is_accepted(settings: Callable[..., Any]) -> None:
    assert settings(market_mcp_url="http://127.0.0.1:8020").market_mcp_url == "http://127.0.0.1:8020"


def test_remote_tool_server_with_a_scope_is_accepted(settings: Callable[..., Any]) -> None:
    resolved = settings(
        market_mcp_url="https://market-mcp.example.com/",
        market_mcp_scope="api://some-app/.default",
    )
    # The trailing slash is dropped here so nothing downstream builds `//mcp`.
    assert resolved.market_mcp_url == "https://market-mcp.example.com"


def test_a_blank_tool_server_url_means_unset(settings: Callable[..., Any]) -> None:
    assert settings(market_mcp_url="   ").market_mcp_url is None
