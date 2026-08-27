"""The refusals that keep a misconfigured process from starting. Unit tests, not `db` ones: the whole
point is that the process never gets that far."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from polymarket_data.config import Settings

LOCAL_URL = "postgresql://polymarket:change-me@127.0.0.1:55432/polymarket"
REMOTE_URL = "postgresql://server.postgres.database.azure.com:5432/polymarket?sslmode=require"


def build(**overrides) -> Settings:
    values = {"database_url": LOCAL_URL} | overrides
    return Settings(_env_file=None, **values)


class TestDatabaseMode:
    def test_local_mode_takes_the_url_verbatim(self):
        settings = build()
        assert settings.database_user is None
        assert settings.database_url == LOCAL_URL

    def test_blank_database_user_means_local_mode(self):
        # `DATABASE_USER=` left in a .env is the same intent as the line being absent —
        # not a role named "".
        assert build(database_user="   ").database_user is None

    def test_local_mode_refuses_a_remote_host(self):
        with pytest.raises(ValidationError, match="no DATABASE_USER"):
            build(database_url=REMOTE_URL)

    def test_identity_mode_requires_tls(self):
        with pytest.raises(ValidationError, match="does not require TLS"):
            build(
                database_url="postgresql://server.postgres.database.azure.com:5432/polymarket",
                database_user="polymarket",
            )

    def test_identity_mode_refuses_a_credential_in_the_url(self):
        with pytest.raises(ValidationError, match="username or password"):
            build(
                database_url=(
                    "postgresql://someone:secret@server.postgres.database.azure.com"
                    ":5432/polymarket?sslmode=require"
                ),
                database_user="polymarket",
            )

    def test_identity_mode_accepts_the_production_shape(self):
        settings = build(database_url=REMOTE_URL, database_user="polymarket")
        assert settings.database_user == "polymarket"


class TestProvider:
    def test_refuses_a_url_without_a_host(self):
        with pytest.raises(ValidationError, match="not a usable URL"):
            build(gamma_base_url="not-a-url")

    def test_refuses_a_scheme_that_is_not_http(self):
        with pytest.raises(ValidationError, match="must be http or https"):
            build(clob_base_url="ftp://clob.polymarket.com")

    def test_trailing_slash_is_dropped(self):
        # So that every call site can join with a leading slash and none has to remember.
        assert build(gamma_base_url="https://example.test/").gamma_base_url == (
            "https://example.test"
        )

    def test_refuses_an_empty_user_agent(self):
        # The provider's edge selects on this header — measured 22 August 2026. An empty setting would
        # send the header empty and leave the module unnamed to a provider that reads it.
        with pytest.raises(ValidationError, match="PROVIDER_USER_AGENT is set but empty"):
            build(provider_user_agent="  ")


class TestBudgets:
    @pytest.mark.parametrize(
        "field",
        [
            "provider_concurrency",
            "sample_interval_seconds",
            "history_window_days",
            "default_backfill_days",
            "max_tracked_events",
        ],
    )
    def test_refuses_zero(self, field: str):
        with pytest.raises(ValidationError, match="must be at least 1"):
            build(**{field: 0})

    def test_history_window_defaults_to_the_measured_provider_cap(self):
        # 15 days passes and 16 does not — measured, and on the time interval rather than
        # the point count. A default that guessed higher would fail every backfill.
        assert build().history_window_days == 15


class TestCallerLists:
    def test_comma_separated_identifiers_become_a_set(self):
        settings = build(tool_caller_application_ids=" a , b ,, c ")
        assert settings.tool_caller_ids == frozenset({"a", "b", "c"})

    def test_empty_list_is_empty_not_everyone(self):
        # The lists are read only where `require_authenticated_principal` is on, and there
        # an empty list must refuse every caller rather than admit all of them.
        assert build().tool_caller_ids == frozenset()
        assert build().rest_caller_ids == frozenset()
