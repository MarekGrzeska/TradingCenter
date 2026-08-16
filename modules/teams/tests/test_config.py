from __future__ import annotations

import pytest
from pydantic import ValidationError

from teams.config import Settings

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

REQUIRED = {
    "database_url": "postgresql://localhost:5432/teams?sslmode=require",
    "database_user": "teams",
    "openai_api_key": "key",
    "models": ONE_MODEL,
}


def settings(**overrides) -> Settings:
    # _env_file=None so a developer's real .env cannot make a test pass or fail.
    return Settings(**{**REQUIRED, **overrides}, _env_file=None)


def test_a_complete_configuration_builds() -> None:
    s = settings()
    assert s.models[0].display_name == "Luna"


# --- database mode, same two failures as market-data's and agent's config.py ---


def test_no_database_user_with_a_loopback_url_is_local_mode() -> None:
    s = settings(
        database_user=None,
        database_url="postgresql://teams:change-me@127.0.0.1:55432/teams",
    )
    assert s.database_user is None


def test_a_blank_database_user_means_local_mode_not_a_role_named_blank() -> None:
    s = settings(
        database_user="   ",
        database_url="postgresql://teams:change-me@localhost:55432/teams",
    )
    assert s.database_user is None


def test_no_database_user_with_a_remote_host_refuses_to_start() -> None:
    with pytest.raises(ValidationError) as err:
        settings(
            database_user=None,
            database_url="postgresql://teams:change-me@psql-tradingcenter.postgres.database.azure.com/teams",
        )
    assert "DATABASE_USER" in str(err.value)
    assert "loopback" in str(err.value)


def test_a_database_url_that_does_not_require_tls_refuses_to_start() -> None:
    with pytest.raises(ValidationError) as err:
        settings(database_url="postgresql://localhost:5432/teams?sslmode=prefer")
    assert "TLS" in str(err.value)


def test_a_database_url_with_a_credential_refuses_to_start() -> None:
    with pytest.raises(ValidationError) as err:
        settings(database_url="postgresql://user:pass@localhost:5432/teams?sslmode=require")
    assert "DATABASE_URL" in str(err.value)


def test_local_mode_does_not_require_tls() -> None:
    url = "postgresql://teams:change-me@127.0.0.1:55432/teams"
    assert settings(database_user=None, database_url=url).database_url == url


# --- provider credential: the key, and nothing to fall back to ---


def test_a_missing_api_key_refuses_to_start() -> None:
    """Not optional, unlike the database's: OpenAI is not in Entra, so there is no
    ambient identity to fall back to when this is absent."""
    incomplete = {k: v for k, v in REQUIRED.items() if k != "openai_api_key"}
    with pytest.raises(ValidationError) as err:
        Settings(**incomplete, _env_file=None)  # pyright: ignore[reportCallIssue]
    assert "openai_api_key" in str(err.value)


def test_a_blank_api_key_is_a_missing_one_not_a_key_named_blank() -> None:
    with pytest.raises(ValidationError) as err:
        settings(openai_api_key="   ")
    assert "OPENAI_API_KEY" in str(err.value)


def test_the_api_key_is_stripped() -> None:
    assert settings(openai_api_key="  sk-abc  ").openai_api_key == "sk-abc"


# --- model catalogue: no default_model_id here, unlike agent's ---


def test_an_empty_catalogue_refuses_to_start() -> None:
    with pytest.raises(ValidationError) as err:
        settings(models=[])
    assert "MODELS" in str(err.value)


def test_duplicate_model_ids_refuse_to_start() -> None:
    with pytest.raises(ValidationError) as err:
        settings(models=ONE_MODEL + ONE_MODEL)
    assert "duplicate" in str(err.value)


def test_a_model_without_a_rate_fails_to_parse() -> None:
    # specs/teams-models, "Model spoza katalogu jest odmową, nie podmianą" — a rate
    # missing entirely must not read as free.
    broken = [{k: v for k, v in ONE_MODEL[0].items() if k != "input_rate_per_1m"}]
    with pytest.raises(ValidationError):
        settings(models=broken)


@pytest.mark.parametrize("field", ["input_rate_per_1m", "output_rate_per_1m"])
def test_a_non_positive_rate_refuses_to_start(field: str) -> None:
    broken = [{**ONE_MODEL[0], field: "0"}]
    with pytest.raises(ValidationError) as err:
        settings(models=broken)
    assert field in str(err.value)


def test_a_missing_database_url_names_itself() -> None:
    with pytest.raises(ValidationError) as err:
        Settings(_env_file=None)
    assert "database_url" in str(err.value)


# --- the tool server's own mode switch (specs/teams-tool-access) ---


def test_no_tool_server_configured_is_a_valid_state() -> None:
    # Not a misconfiguration: a team whose agents carry no assigned tools never needs
    # one, and a team that does is refused at run time, not at startup.
    assert settings().market_mcp_url is None


def test_remote_tool_server_without_a_scope_is_refused() -> None:
    with pytest.raises(ValidationError) as err:
        settings(market_mcp_url="https://market-mcp.example.com")
    assert "MARKET_MCP_SCOPE" in str(err.value)


def test_scope_with_a_loopback_tool_server_is_refused() -> None:
    with pytest.raises(ValidationError) as err:
        settings(
            market_mcp_url="http://127.0.0.1:8040",
            market_mcp_scope="api://some-app/.default",
        )
    assert "loopback" in str(err.value)


def test_a_scope_with_no_url_at_all_is_refused() -> None:
    with pytest.raises(ValidationError) as err:
        settings(market_mcp_scope="api://some-app/.default")
    assert "MARKET_MCP_URL" in str(err.value)


def test_loopback_tool_server_without_a_scope_is_accepted() -> None:
    assert settings(market_mcp_url="http://127.0.0.1:8040").market_mcp_url == (
        "http://127.0.0.1:8040"
    )


def test_remote_tool_server_with_a_scope_is_accepted() -> None:
    resolved = settings(
        market_mcp_url="https://market-mcp.example.com/",
        market_mcp_scope="api://some-app/.default",
    )
    # The trailing slash is dropped here so nothing downstream builds `//mcp`.
    assert resolved.market_mcp_url == "https://market-mcp.example.com"


def test_a_blank_tool_server_url_means_unset() -> None:
    assert settings(market_mcp_url="   ").market_mcp_url is None


# --- the second tool server, checked independently (specs/teams-tool-access,
# "Moduł MAY być skonfigurowany z więcej niż jednym serwerem narzędzi") ---


def test_no_trading_mcp_configured_is_a_valid_state() -> None:
    assert settings().trading_mcp_url is None


def test_remote_trading_mcp_without_a_scope_is_refused() -> None:
    with pytest.raises(ValidationError) as err:
        settings(trading_mcp_url="https://trading-mcp.example.com")
    assert "TRADING_MCP_SCOPE" in str(err.value)


def test_scope_with_a_loopback_trading_mcp_is_refused() -> None:
    with pytest.raises(ValidationError) as err:
        settings(
            trading_mcp_url="http://127.0.0.1:8060",
            trading_mcp_scope="api://some-app/.default",
        )
    assert "loopback" in str(err.value)


def test_loopback_trading_mcp_without_a_scope_is_accepted() -> None:
    assert settings(trading_mcp_url="http://127.0.0.1:8060").trading_mcp_url == (
        "http://127.0.0.1:8060"
    )


def test_remote_trading_mcp_with_a_scope_is_accepted() -> None:
    resolved = settings(
        trading_mcp_url="https://trading-mcp.example.com/",
        trading_mcp_scope="api://some-app/.default",
    )
    assert resolved.trading_mcp_url == "https://trading-mcp.example.com"


def test_a_blank_trading_mcp_url_means_unset() -> None:
    assert settings(trading_mcp_url="   ").trading_mcp_url is None


def test_one_valid_server_and_one_broken_server_is_refused_naming_the_broken_one() -> None:
    """specs/teams-tool-access, "Niespójność dotyczy drugiego serwera": market-mcp is
    fine here, and the refusal has to say it is trading-mcp's configuration that is
    not — an operator fixing the wrong one would still be stuck."""
    with pytest.raises(ValidationError) as err:
        settings(
            market_mcp_url="http://127.0.0.1:8040",
            trading_mcp_url="https://trading-mcp.example.com",
        )
    message = str(err.value)
    assert "TRADING_MCP_SCOPE" in message
    assert "MARKET_MCP_SCOPE" not in message


def test_both_servers_configured_independently_is_accepted() -> None:
    resolved = settings(
        market_mcp_url="http://127.0.0.1:8040",
        trading_mcp_url="https://trading-mcp.example.com",
        trading_mcp_scope="api://some-app/.default",
    )
    assert resolved.market_mcp_url == "http://127.0.0.1:8040"
    assert resolved.trading_mcp_url == "https://trading-mcp.example.com"
