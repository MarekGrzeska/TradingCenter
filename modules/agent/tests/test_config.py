from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent.config import Settings

ONE_MODEL = [
    {
        "id": "gpt-5.6-luna",
        "deployment": "luna-prod",
        "display_name": "Luna",
        "cost_rank": 1,
        "input_rate_per_1k": "0.001",
        "output_rate_per_1k": "0.006",
    }
]

REQUIRED = {
    "database_url": "postgresql://localhost:5432/agent?sslmode=require",
    "database_user": "agent",
    "azure_openai_endpoint": "https://example.openai.azure.com",
    "azure_openai_api_version": "2026-01-01",
    "azure_openai_api_key": "key",
    "models": ONE_MODEL,
    "default_model_id": "gpt-5.6-luna",
}


def settings(**overrides) -> Settings:
    # _env_file=None so a developer's real .env cannot make a test pass or fail.
    return Settings(**{**REQUIRED, **overrides}, _env_file=None)


def test_a_complete_configuration_builds() -> None:
    s = settings()
    assert s.default_model_id == "gpt-5.6-luna"
    assert s.models[0].display_name == "Luna"


# --- database mode, same two failures as market-data/config.py ---


def test_no_database_user_with_a_loopback_url_is_local_mode() -> None:
    s = settings(
        database_user=None,
        database_url="postgresql://agent:change-me@127.0.0.1:55432/agent",
    )
    assert s.database_user is None


def test_a_blank_database_user_means_local_mode_not_a_role_named_blank() -> None:
    s = settings(
        database_user="   ",
        database_url="postgresql://agent:change-me@localhost:55432/agent",
    )
    assert s.database_user is None


def test_no_database_user_with_a_remote_host_refuses_to_start() -> None:
    with pytest.raises(ValidationError) as err:
        settings(
            database_user=None,
            database_url="postgresql://agent:change-me@psql-tradingcenter.postgres.database.azure.com/agent",
        )
    assert "DATABASE_USER" in str(err.value)
    assert "loopback" in str(err.value)


def test_a_database_url_that_does_not_require_tls_refuses_to_start() -> None:
    with pytest.raises(ValidationError) as err:
        settings(database_url="postgresql://localhost:5432/agent?sslmode=prefer")
    assert "TLS" in str(err.value)


def test_a_database_url_with_a_credential_refuses_to_start() -> None:
    with pytest.raises(ValidationError) as err:
        settings(database_url="postgresql://user:pass@localhost:5432/agent?sslmode=require")
    assert "DATABASE_URL" in str(err.value)


def test_local_mode_does_not_require_tls() -> None:
    url = "postgresql://agent:change-me@127.0.0.1:55432/agent"
    assert settings(database_user=None, database_url=url).database_url == url


# --- provider mode: exactly one of key / managed identity ---


def test_key_and_managed_identity_together_refuses_to_start() -> None:
    with pytest.raises(ValidationError) as err:
        settings(azure_openai_api_key="key", azure_openai_use_managed_identity=True)
    assert "exactly one" in str(err.value)


def test_neither_key_nor_managed_identity_refuses_to_start() -> None:
    with pytest.raises(ValidationError) as err:
        settings(azure_openai_api_key=None, azure_openai_use_managed_identity=False)
    assert "AZURE_OPENAI_API_KEY" in str(err.value)


def test_managed_identity_alone_is_a_valid_mode() -> None:
    s = settings(azure_openai_api_key=None, azure_openai_use_managed_identity=True)
    assert s.azure_openai_api_key is None
    assert s.azure_openai_use_managed_identity is True


def test_a_blank_api_key_means_unset_not_a_key_named_blank() -> None:
    with pytest.raises(ValidationError) as err:
        settings(azure_openai_api_key="   ", azure_openai_use_managed_identity=False)
    assert "AZURE_OPENAI_API_KEY" in str(err.value)


# --- model catalogue ---


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
    broken = [{k: v for k, v in ONE_MODEL[0].items() if k != "input_rate_per_1k"}]
    with pytest.raises(ValidationError):
        settings(models=broken)


@pytest.mark.parametrize("field", ["input_rate_per_1k", "output_rate_per_1k"])
def test_a_non_positive_rate_refuses_to_start(field: str) -> None:
    broken = [{**ONE_MODEL[0], field: "0"}]
    with pytest.raises(ValidationError) as err:
        settings(models=broken)
    assert field in str(err.value)


def test_a_missing_database_url_names_itself() -> None:
    with pytest.raises(ValidationError) as err:
        Settings(_env_file=None)
    assert "database_url" in str(err.value)
