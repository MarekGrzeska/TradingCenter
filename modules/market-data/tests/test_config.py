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


def test_defaults_point_at_a_local_gateway() -> None:
    s = settings()
    assert s.gateway_base_url == "http://localhost:8010"
    assert s.gateway_stream_url == "ws://localhost:8010/ws/stream"


def test_one_fill_at_a_time_by_default() -> None:
    # Two deep fills sharing the gateway's 10 req/s gate starve the chart an operator is
    # watching. The safe number is the default, and raising it has to be deliberate.
    assert settings().backfill_concurrency == 1


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
    # The guard reads the host, not the whole string: a gateway deployed under a path
    # that happens to carry the provider's name is still the gateway.
    url = "https://gw.internal.test/proxy/capital.com"
    assert settings(gateway_base_url=url).gateway_base_url == url


def test_a_trailing_slash_is_not_a_different_host() -> None:
    assert settings(gateway_base_url="http://localhost:8010/").gateway_base_url == (
        "http://localhost:8010"
    )


@pytest.mark.parametrize("url", ["", "   ", "not-a-url"])
def test_an_unusable_gateway_url_names_itself(url: str) -> None:
    with pytest.raises(ValidationError) as err:
        settings(gateway_base_url=url)
    assert "GATEWAY_BASE_URL" in str(err.value)


def test_a_missing_database_url_names_itself() -> None:
    with pytest.raises(ValidationError) as err:
        Settings(_env_file=None)
    assert "database_url" in str(err.value)


def test_a_blank_database_url_names_itself() -> None:
    # An unfilled .env sets the variable to "" rather than leaving it out, which pydantic
    # accepts as a string. Without this the module starts and fails at the first query.
    with pytest.raises(ValidationError) as err:
        settings(database_url="   ")
    assert "DATABASE_URL" in str(err.value)


def test_a_missing_gateway_api_key_names_itself() -> None:
    # A module that started without it would run and archive nothing — capital-gateway
    # answers 401 to every call, silently, hours before anyone notices the archive is
    # not growing. Refusing to start turns that into an immediate, named failure.
    with pytest.raises(ValidationError) as err:
        Settings(
            database_url=REQUIRED["database_url"],
            database_user=REQUIRED["database_user"],
            _env_file=None,
        )
    assert "gateway_api_key" in str(err.value)


def test_a_blank_gateway_api_key_names_itself() -> None:
    with pytest.raises(ValidationError) as err:
        settings(gateway_api_key="   ")
    assert "GATEWAY_API_KEY" in str(err.value)


@pytest.mark.parametrize(
    "field", ["backfill_concurrency", "default_backfill_bars", "max_tracked_pairs"]
)
def test_a_budget_below_one_names_itself(field: str) -> None:
    with pytest.raises(ValidationError) as err:
        settings(**{field: 0})
    assert field.upper() in str(err.value)


# specs/market-data-database-connection/spec.md, "Praca bez tożsamości nie wychodzi poza
# maszynę" — DATABASE_USER selects the mode, and its absence narrows the module to loopback.


def test_no_database_user_with_a_loopback_url_is_local_mode() -> None:
    s = Settings(
        database_url="postgresql://market_data:change-me@127.0.0.1:55432/market_data",
        gateway_api_key="k",
        _env_file=None,
    )
    assert s.database_user is None


def test_a_blank_database_user_means_local_mode_not_a_role_named_blank() -> None:
    # An unfilled `DATABASE_USER=` line in a .env is the same intent as the line being
    # absent — not an identity called "".
    s = settings(
        database_user="   ",
        database_url="postgresql://market_data:change-me@localhost:55432/market_data",
    )
    assert s.database_user is None


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://market_data:change-me@psql-tradingcenter.postgres.database.azure.com:5432/market_data",
        "postgresql://db.internal.test:5432/market_data?sslmode=require",
    ],
)
def test_no_database_user_with_a_remote_host_refuses_to_start(url: str) -> None:
    # The quiet disaster this refuses: a .env aimed at production while nothing selects
    # an identity — the module would otherwise write to the wrong database, or worse,
    # authenticate as whatever ambient credential the machine happens to hold.
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


@pytest.mark.parametrize("sslmode", ["require", "verify-ca", "verify-full"])
def test_a_database_url_that_requires_tls_is_accepted(sslmode: str) -> None:
    url = f"postgresql://localhost:5432/market_data?sslmode={sslmode}"
    assert settings(database_url=url).database_url == url


# specs/market-data-database-connection/spec.md, "Moduł przedstawia się tożsamością, nie
# hasłem" — a credential in the URL is not read, so leaving one there is rejected rather
# than silently ignored.
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
