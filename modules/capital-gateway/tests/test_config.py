from __future__ import annotations

import pytest
from pydantic import ValidationError

from capital_gateway.config import (
    DEMO_BASE_URL,
    DEMO_STREAM_URL,
    Settings,
    environment_of,
)

CREDS = {
    "capital_api_key": "k",
    "capital_identifier": "me@example.com",
    "capital_password": "p",
    "gateway_api_key": "g",
}


def settings(**overrides) -> Settings:
    # _env_file=None so a developer's real .env cannot make a test pass or fail.
    return Settings(**{**CREDS, **overrides}, _env_file=None)


def test_defaults_are_the_demo_endpoints() -> None:
    s = settings()
    assert s.capital_base_url == DEMO_BASE_URL
    assert s.capital_stream_url == DEMO_STREAM_URL


@pytest.mark.parametrize(
    "url",
    [
        "https://api-capital.backend-capital.com",
        # The live host with the demo host as a suffix — a substring test would pass this.
        "https://api-capital.backend-capital.com/?x=demo-api-capital.backend-capital.com",
        "https://demo-api-capital.backend-capital.com.evil.test",
    ],
)
def test_a_non_demo_base_url_refuses_to_start(url: str) -> None:
    with pytest.raises(ValidationError) as err:
        settings(capital_base_url=url)
    assert "demo" in str(err.value)
    assert "CAPITAL_BASE_URL" in str(err.value)


def test_a_non_demo_stream_url_refuses_to_start() -> None:
    with pytest.raises(ValidationError) as err:
        settings(capital_stream_url="wss://api-streaming-capital.backend-capital.com/live")
    assert "CAPITAL_STREAM_URL" in str(err.value)


def test_a_trailing_slash_is_not_a_different_host() -> None:
    assert settings(capital_base_url=f"{DEMO_BASE_URL}/").capital_base_url == DEMO_BASE_URL


@pytest.mark.parametrize(
    "field", ["capital_api_key", "capital_identifier", "capital_password", "gateway_api_key"]
)
def test_a_missing_credential_names_itself(field: str) -> None:
    with pytest.raises(ValidationError) as err:
        Settings(**{k: v for k, v in CREDS.items() if k != field}, _env_file=None)
    assert field in str(err.value)


@pytest.mark.parametrize(
    "field", ["capital_api_key", "capital_identifier", "capital_password", "gateway_api_key"]
)
def test_a_blank_credential_names_itself(field: str) -> None:
    # An unfilled .env sets the variable to "" rather than leaving it out, which pydantic
    # accepts as a string. Without this the module would start and fail at the first login.
    with pytest.raises(ValidationError) as err:
        settings(**{field: "   "})
    assert field.upper() in str(err.value)


# --- the environment a consumer reads is the host this module is bound to ------------


def test_the_demo_host_is_the_demo_environment() -> None:
    assert environment_of(DEMO_BASE_URL) == "demo"
    assert environment_of(f"{DEMO_BASE_URL}/") == "demo"


def test_any_other_host_is_not() -> None:
    """`Settings` refuses to start on one, so this cannot happen in a running process —
    which is exactly why the value has to be derived rather than declared: the field
    `trading-mcp` reads before it opens a port has to be able to come out differently."""
    assert environment_of("https://api-capital.backend-capital.com") == "live"
