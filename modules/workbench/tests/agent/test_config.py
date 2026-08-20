"""What the conversation's settings hold that the teams surface's do not.

The database-mode rules and the market-mcp mode switch are the same validators on both
surfaces and are checked once for both, in `tests/test_config_common.py`.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent.config import Settings

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
    "database_url": "postgresql://localhost:5432/agent?sslmode=require",
    "database_user": "agent",
    "openai_api_key": "key",
    "models": ONE_MODEL,
    "default_model_id": "gpt-5.6-luna",
}


def settings(**overrides) -> Settings:
    # _env_file=None so a developer's real .env cannot make a test pass or fail.
    return Settings(**{**REQUIRED, **overrides}, _env_file=None)


def test_a_complete_configuration_names_its_default_model() -> None:
    assert settings().default_model_id == "gpt-5.6-luna"


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


# --- model catalogue, and the default this surface alone has ---


def test_an_empty_catalogue_refuses_to_start() -> None:
    with pytest.raises(ValidationError) as err:
        settings(models=[], default_model_id="gpt-5.6-luna")
    assert "MODELS" in str(err.value)


def test_duplicate_model_ids_refuse_to_start() -> None:
    with pytest.raises(ValidationError) as err:
        settings(models=ONE_MODEL + ONE_MODEL)
    assert "duplicate" in str(err.value)


def test_default_model_outside_the_catalogue_refuses_to_start() -> None:
    with pytest.raises(ValidationError) as err:
        settings(default_model_id="gpt-5.6-sol")
    assert "DEFAULT_MODEL_ID" in str(err.value)


def test_a_model_without_a_rate_fails_to_parse() -> None:
    # specs/agent-models, "Model spoza katalogu jest odmową, nie podmianą" — a rate
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
