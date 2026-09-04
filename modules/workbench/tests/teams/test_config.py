"""What the teams surface's settings hold that the conversation's do not. The database-mode rules and the
tool-server mode switch are the same validators on both and are checked once for both."""

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


# Each server's own mode switch is one rule tested once over every server. What is left here is the part
# that only exists because there is more than one: that a refusal names the one at fault.


def test_one_valid_server_and_one_broken_server_is_refused_naming_the_broken_one() -> None:
    """market-mcp is fine here, and the refusal has to say it is trading-mcp's configuration that is not —
    an operator fixing the wrong one would still be stuck."""
    with pytest.raises(ValidationError) as err:
        settings(
            market_mcp_url="http://127.0.0.1:8020",
            trading_mcp_url="https://trading-mcp.example.com",
        )
    message = str(err.value)
    assert "TRADING_MCP_SCOPE" in message
    assert "MARKET_MCP_SCOPE" not in message


def test_every_server_configured_independently_is_accepted() -> None:
    resolved = settings(
        market_mcp_url="http://127.0.0.1:8020",
        trading_mcp_url="https://trading-mcp.example.com",
        trading_mcp_scope="api://some-app/.default",
        telegram_mcp_url="http://127.0.0.1:8100",
    )
    assert resolved.market_mcp_url == "http://127.0.0.1:8020"
    assert resolved.trading_mcp_url == "https://trading-mcp.example.com"
    assert resolved.telegram_mcp_url == "http://127.0.0.1:8100"


def test_two_servers_configured_and_the_third_unset_is_accepted() -> None:
    """The state a deployment is in between the module going live and the operator's apply: the third
    address is simply not there yet, and that is a configuration, not a half-finished one."""
    resolved = settings(
        market_mcp_url="http://127.0.0.1:8020",
        trading_mcp_url="http://127.0.0.1:8060",
    )
    assert resolved.telegram_mcp_url is None
