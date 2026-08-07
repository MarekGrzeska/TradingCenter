from __future__ import annotations

import pytest
from pydantic import ValidationError

from market_data.config import Settings

REQUIRED = {"database_url": "postgresql://u:p@localhost:5432/market_data"}


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


@pytest.mark.parametrize(
    "field", ["backfill_concurrency", "default_backfill_bars", "max_tracked_pairs"]
)
def test_a_budget_below_one_names_itself(field: str) -> None:
    with pytest.raises(ValidationError) as err:
        settings(**{field: 0})
    assert field.upper() in str(err.value)


@pytest.mark.db
def test_the_test_database_is_reachable_and_empty(postgres_url: str) -> None:
    """The harness itself, proven once: a container comes up and has no tables yet.

    Everything under the `db` marker builds on this, so its failure should point here
    rather than at whichever migration test happened to run first.
    """
    import psycopg

    with psycopg.connect(postgres_url) as conn:
        rows = conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ).fetchall()
    assert rows == []
