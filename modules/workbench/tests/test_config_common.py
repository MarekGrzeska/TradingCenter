"""The settings rules both surfaces carry identically, checked once for both: the classes stay separate, since the
prefixed names are what is doubled, but two validator blocks were byte-identical apart from a word inside a URL."""

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


# Parameterised over the servers rather than copied per server, since the rule is one `_checked_server` call each and
# the third and fourth servers added later would each have been that copy. Each surface's own test_config keeps what is genuinely its own.


@pytest.fixture(
    params=["market_mcp", "trading_mcp", "telegram_mcp"]
)
def server(request: pytest.FixtureRequest) -> str:
    return request.param


def test_no_tool_server_configured_is_a_valid_state(
    settings: Callable[..., Any], server: str
) -> None:
    # Not a misconfiguration: it is what the conversation was before it had tools, and for
    # teams it is what a team carrying no assigned tools never needs.
    assert getattr(settings(), f"{server}_url") is None


def test_remote_tool_server_without_a_scope_is_refused(
    settings: Callable[..., Any], server: str
) -> None:
    with pytest.raises(ValidationError) as err:
        settings(**{f"{server}_url": "https://tools.example.com"})
    assert f"{server.upper()}_SCOPE" in str(err.value)


def test_scope_with_a_loopback_tool_server_is_refused(
    settings: Callable[..., Any], server: str
) -> None:
    with pytest.raises(ValidationError) as err:
        settings(
            **{
                f"{server}_url": "http://127.0.0.1:8020",
                f"{server}_scope": "api://some-app/.default",
            }
        )
    assert "loopback" in str(err.value)


def test_a_scope_with_no_url_at_all_is_refused(
    settings: Callable[..., Any], server: str
) -> None:
    with pytest.raises(ValidationError) as err:
        settings(**{f"{server}_scope": "api://some-app/.default"})
    assert f"{server.upper()}_URL" in str(err.value)


def test_loopback_tool_server_without_a_scope_is_accepted(
    settings: Callable[..., Any], server: str
) -> None:
    resolved = settings(**{f"{server}_url": "http://127.0.0.1:8020"})
    assert getattr(resolved, f"{server}_url") == "http://127.0.0.1:8020"


def test_remote_tool_server_with_a_scope_is_accepted(
    settings: Callable[..., Any], server: str
) -> None:
    resolved = settings(
        **{
            f"{server}_url": "https://tools.example.com/",
            f"{server}_scope": "api://some-app/.default",
        }
    )
    # The trailing slash is dropped here so nothing downstream builds `//mcp`.
    assert getattr(resolved, f"{server}_url") == "https://tools.example.com"


def test_a_blank_tool_server_url_means_unset(
    settings: Callable[..., Any], server: str
) -> None:
    assert getattr(settings(**{f"{server}_url": "   "}), f"{server}_url") is None
