from __future__ import annotations

import pytest
from pydantic import ValidationError

from trading_mcp.config import Settings


def test_missing_gateway_key_is_refused() -> None:
    with pytest.raises(ValidationError):
        Settings(capital_gateway_url="http://127.0.0.1:8010", _env_file=None)  # type: ignore[call-arg]


def test_blank_gateway_key_is_refused() -> None:
    with pytest.raises(ValidationError, match="CAPITAL_GATEWAY_API_KEY"):
        Settings(
            capital_gateway_url="http://127.0.0.1:8010",
            capital_gateway_api_key="   ",
            _env_file=None,  # type: ignore[call-arg]
        )


def test_gateway_key_required_even_at_loopback() -> None:
    """Unlike market-mcp's upstream mode, there is no loopback exemption here —
    capital-gateway checks the same header from every caller (specs/
    trading-mcp-upstream-access, "Poświadczenie do gatewaya jest wymagane
    niezależnie od adresu")."""
    with pytest.raises(ValidationError):
        Settings(capital_gateway_url="http://127.0.0.1:8010", _env_file=None)  # type: ignore[call-arg]


def test_valid_settings_are_accepted() -> None:
    settings = Settings(
        capital_gateway_url="http://127.0.0.1:8010",
        capital_gateway_api_key="a-real-key",
        _env_file=None,  # type: ignore[call-arg]
    )
    assert settings.capital_gateway_api_key == "a-real-key"


def test_the_http_transport_binds_loopback_unless_told_otherwise() -> None:
    settings = Settings(capital_gateway_api_key="a-real-key", _env_file=None)  # type: ignore[call-arg]
    assert settings.trading_mcp_host == "127.0.0.1"


def test_default_port_is_8060() -> None:
    settings = Settings(capital_gateway_api_key="a-real-key", _env_file=None)  # type: ignore[call-arg]
    assert settings.trading_mcp_port == 8060
