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


def test_an_absent_operator_is_tolerated_only_in_the_full_local_shape() -> None:
    """specs/teams-mcp-authorship — both conditions, and each one alone is not enough."""
    local = _settings(teams_url="http://127.0.0.1:8050")
    assert local.operator_identity_optional is True


def test_an_authenticator_in_front_makes_an_operator_required_even_on_loopback() -> None:
    guarded = _settings(teams_url="http://127.0.0.1:8050", require_authenticated_principal=True)
    assert guarded.operator_identity_optional is False


def test_a_remote_teams_makes_an_operator_required_even_with_no_authenticator() -> None:
    # The half that catches the shape design.md names: an instance with the flag off
    # pointed at a teams that is not on this machine.
    remote = _settings(
        teams_url="https://app-tradingcenter-teams.azurewebsites.net",
        teams_scope="api://tradingcenter-teams/.default",
        require_authenticated_principal=False,
    )
    assert remote.operator_identity_optional is False


def test_the_deployed_shape_requires_an_operator_on_both_counts() -> None:
    deployed = _settings(
        teams_url="https://app-tradingcenter-teams.azurewebsites.net",
        teams_scope="api://tradingcenter-teams/.default",
        require_authenticated_principal=True,
    )
    assert deployed.operator_identity_optional is False


def test_localhost_and_ipv6_loopback_count_as_this_machine() -> None:
    assert _settings(teams_url="http://localhost:8050").operator_identity_optional is True
    assert _settings(teams_url="http://[::1]:8050").operator_identity_optional is True


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
