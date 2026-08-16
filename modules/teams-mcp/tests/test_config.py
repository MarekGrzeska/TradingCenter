"""specs/teams-mcp-upstream-access, "Tryb połączenia jest wybrany jednoznacznie, nie
zgadnięty" — the switch is refused at startup rather than guessed at, so a misconfigured
module never reaches the point of writing anything in an operator's name."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from teams_mcp.config import Settings


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def test_loopback_without_a_scope_is_the_local_mode() -> None:
    settings = _settings(teams_url="http://127.0.0.1:8050")
    assert settings.teams_scope is None
    assert settings.teams_mcp_port == 8070


def test_a_remote_url_without_a_scope_is_refused_naming_the_setting() -> None:
    with pytest.raises(ValidationError) as err:
        _settings(teams_url="https://app-tradingcenter-teams.azurewebsites.net")

    assert "TEAMS_SCOPE" in str(err.value)


def test_a_scope_against_loopback_is_refused_rather_than_ignored() -> None:
    with pytest.raises(ValidationError) as err:
        _settings(teams_url="http://127.0.0.1:8050", teams_scope="api://teams/.default")

    assert "loopback" in str(err.value)


def test_a_remote_url_with_a_scope_is_the_deployed_mode() -> None:
    settings = _settings(
        teams_url="https://app-tradingcenter-teams.azurewebsites.net",
        teams_scope="api://tradingcenter-teams/.default",
    )
    assert settings.teams_scope == "api://tradingcenter-teams/.default"


def test_an_empty_scope_reads_as_unset_not_as_a_scope_named_nothing() -> None:
    # TEAMS_SCOPE= left in a .env is the same intent as the line being absent.
    settings = _settings(teams_url="http://127.0.0.1:8050", teams_scope="   ")
    assert settings.teams_scope is None


def test_a_blank_url_is_refused() -> None:
    with pytest.raises(ValidationError):
        _settings(teams_url="   ")


def test_a_timeout_of_zero_is_refused() -> None:
    with pytest.raises(ValidationError) as err:
        _settings(teams_request_timeout_seconds=0)

    assert "TEAMS_REQUEST_TIMEOUT_SECONDS" in str(err.value)
