from __future__ import annotations

import pytest
from pydantic import ValidationError

from market_data.config import Settings

REQUIRED = {
    "database_url": "postgresql://localhost:5432/market_data?sslmode=require",
    "database_user": "market_data",
    "gateway_api_key": "gateway-caller-key",
}


def settings(**overrides) -> Settings:
    # _env_file=None so a developer's real .env cannot make a test pass or fail.
    return Settings(**{**REQUIRED, **overrides}, _env_file=None)



@pytest.mark.parametrize(
    "url",
    [
        "https://demo-api-capital.backend-capital.com",
        "https://api-capital.backend-capital.com",
        "https://CAPITAL.COM",
    ],
)
def test_a_base_url_on_the_provider_refuses_to_start(url: str) -> None:
    with pytest.raises(ValidationError) as err:
        settings(gateway_base_url=url)
    assert "GATEWAY_BASE_URL" in str(err.value)
    assert "capital-gateway" in str(err.value)


def test_a_stream_url_on_the_provider_refuses_to_start() -> None:
    with pytest.raises(ValidationError) as err:
        settings(gateway_stream_url="wss://api-streaming-capital.backend-capital.com/connect")
    assert "GATEWAY_STREAM_URL" in str(err.value)


def test_a_host_merely_mentioning_the_provider_in_its_path_is_allowed() -> None:
    # The guard reads the host, not the whole string: a gateway deployed under a path carrying the
    # provider's name is still the gateway. Without this, a guard refusing everything would pass.
    url = "https://gw.internal.test/proxy/capital.com"
    assert settings(gateway_base_url=url).gateway_base_url == url


# specs/market-data-database-connection/spec.md, "Praca bez tożsamości nie wychodzi poza
# maszynę" — DATABASE_USER selects the mode, and its absence narrows the module to loopback.


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://market_data:change-me@psql-tradingcenter.postgres.database.azure.com:5432/market_data",
        "postgresql://db.internal.test:5432/market_data?sslmode=require",
    ],
)
def test_no_database_user_with_a_remote_host_refuses_to_start(url: str) -> None:
    # The quiet disaster this refuses: a .env aimed at production while nothing selects an identity,
    # so the module writes to the wrong database or authenticates as an ambient credential.
    with pytest.raises(ValidationError) as err:
        settings(database_user=None, database_url=url)
    assert "DATABASE_USER" in str(err.value)
    assert "loopback" in str(err.value)


def test_local_mode_does_not_require_tls() -> None:
    # The TLS requirement's own rationale — traffic crossing a network the module does
    # not control — does not hold on loopback (delta spec, "Baza lokalna bez szyfrowania").
    url = "postgresql://market_data:change-me@127.0.0.1:55432/market_data"
    assert settings(database_user=None, database_url=url).database_url == url


# specs/market-data-database-connection/spec.md, "Połączenie z bazą jest szyfrowane".
@pytest.mark.parametrize(
    "url",
    [
        "postgresql://localhost:5432/market_data",  # no sslmode at all
        "postgresql://localhost:5432/market_data?sslmode=disable",
        "postgresql://localhost:5432/market_data?sslmode=allow",
        "postgresql://localhost:5432/market_data?sslmode=prefer",  # still downgrades
    ],
)
def test_a_database_url_that_does_not_require_tls_refuses_to_start(url: str) -> None:
    with pytest.raises(ValidationError) as err:
        settings(database_url=url)
    assert "DATABASE_URL" in str(err.value)
    assert "TLS" in str(err.value)


# specs/market-data-database-connection, "Moduł przedstawia się tożsamością, nie hasłem" — a
# credential in the URL is not read, so leaving one there is rejected rather than silently ignored.
@pytest.mark.parametrize(
    "url",
    [
        "postgresql://user:pass@localhost:5432/market_data?sslmode=require",
        "postgresql://justauser@localhost:5432/market_data?sslmode=require",
    ],
)
def test_a_database_url_with_a_credential_refuses_to_start(url: str) -> None:
    with pytest.raises(ValidationError) as err:
        settings(database_url=url)
    assert "DATABASE_URL" in str(err.value)
