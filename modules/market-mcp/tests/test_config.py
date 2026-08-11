from __future__ import annotations

import pytest
from pydantic import ValidationError

from market_mcp.config import Settings


def test_loopback_without_scope_is_local_mode() -> None:
    settings = Settings(market_data_url="http://127.0.0.1:8020", _env_file=None)  # type: ignore[call-arg]
    assert settings.market_data_scope is None


def test_remote_url_without_scope_is_refused() -> None:
    with pytest.raises(ValidationError, match="MARKET_DATA_SCOPE"):
        Settings(market_data_url="https://market-data.example.com", _env_file=None)  # type: ignore[call-arg]


def test_scope_with_loopback_url_is_refused() -> None:
    with pytest.raises(ValidationError, match="loopback"):
        Settings(
            market_data_url="http://127.0.0.1:8020",
            market_data_scope="api://some-app/.default",
            _env_file=None,  # type: ignore[call-arg]
        )


def test_remote_url_with_scope_is_accepted() -> None:
    settings = Settings(
        market_data_url="https://market-data.example.com",
        market_data_scope="api://some-app/.default",
        _env_file=None,  # type: ignore[call-arg]
    )
    assert settings.market_data_scope == "api://some-app/.default"


def test_blank_scope_means_unset() -> None:
    settings = Settings(
        market_data_url="http://127.0.0.1:8020",
        market_data_scope="   ",
        _env_file=None,  # type: ignore[call-arg]
    )
    assert settings.market_data_scope is None
