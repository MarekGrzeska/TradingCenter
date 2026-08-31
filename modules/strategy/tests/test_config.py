"""The refusals. Every one of these is a configuration that would otherwise look like it
works — which is the only kind worth a test (`strategy-database-connection`)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from strategy.config import Settings


def build(**overrides) -> Settings:
    values = {"database_url": "postgresql://u:p@127.0.0.1:55432/strategy"}
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


class TestTheDatabaseRule:
    def test_local_mode_accepts_loopback_with_a_password(self) -> None:
        settings = build()
        assert settings.database_user is None

    def test_local_mode_refuses_a_remote_host(self) -> None:
        with pytest.raises(ValidationError) as refused:
            build(database_url="postgresql://u:p@db.example.com:5432/strategy")
        assert "loopback" in str(refused.value)

    def test_identity_mode_refuses_a_url_without_tls(self) -> None:
        with pytest.raises(ValidationError) as refused:
            build(
                database_url="postgresql://db.example.com:5432/strategy",
                database_user="strategy-app",
            )
        assert "encrypted" in str(refused.value)

    def test_identity_mode_refuses_a_credential_in_the_url(self) -> None:
        with pytest.raises(ValidationError) as refused:
            build(
                database_url="postgresql://u:p@db.example.com:5432/strategy?sslmode=require",
                database_user="strategy-app",
            )
        assert "username or password" in str(refused.value)

    def test_identity_mode_accepts_tls_without_a_credential(self) -> None:
        settings = build(
            database_url="postgresql://db.example.com:5432/strategy?sslmode=require",
            database_user="strategy-app",
        )
        assert settings.database_user == "strategy-app"

    def test_an_empty_database_user_means_local_mode(self) -> None:
        # `DATABASE_USER=` left in a .env is the same intent as the line being absent.
        assert build(database_user="  ").database_user is None

    def test_an_empty_database_url_is_refused(self) -> None:
        with pytest.raises(ValidationError) as refused:
            build(database_url="   ")
        assert "set but empty" in str(refused.value)


class TestTheUpstream:
    def test_a_url_without_a_host_is_refused(self) -> None:
        with pytest.raises(ValidationError) as refused:
            build(market_data_url="not-a-url")
        assert "not a usable URL" in str(refused.value)

    def test_a_non_http_scheme_is_refused(self) -> None:
        # The archive is reached over its REST contract; a `ws://` here is a setting
        # copied from the wrong line.
        with pytest.raises(ValidationError) as refused:
            build(market_data_url="ws://127.0.0.1:8020")
        assert "http or https" in str(refused.value)

    def test_a_trailing_slash_is_dropped(self) -> None:
        assert build(market_data_url="http://127.0.0.1:8020/").market_data_url == (
            "http://127.0.0.1:8020"
        )


class TestTheLoop:
    def test_a_non_positive_interval_is_refused(self) -> None:
        with pytest.raises(ValidationError) as refused:
            build(evaluation_interval_seconds=0)
        assert "at least 1" in str(refused.value)


class TestCallerLists:
    def test_blanks_and_spacing_are_dropped(self) -> None:
        settings = build(tool_caller_application_ids=" a , ,b ", rest_caller_application_ids="")
        assert settings.tool_caller_ids == {"a", "b"}
        assert settings.rest_caller_ids == frozenset()


class TestTheGateway:
    """Each partial form is silence that reads like a working configuration, so each is refused at
    startup rather than at the first decision worth telling somebody about."""

    def test_all_three_absent_is_a_working_configuration(self) -> None:
        assert build().alerts_configured is False

    def test_a_destination_with_no_gateway_is_refused(self) -> None:
        with pytest.raises(ValidationError) as refused:
            build(alert_destination="operator")
        assert "TELEGRAM_GATEWAY_URL" in str(refused.value)

    def test_a_gateway_with_no_destination_is_refused(self) -> None:
        with pytest.raises(ValidationError) as refused:
            build(telegram_gateway_url="http://127.0.0.1:8100")
        assert "ALERT_DESTINATION" in str(refused.value)

    def test_a_gateway_off_this_machine_without_a_scope_is_refused(self) -> None:
        with pytest.raises(ValidationError) as refused:
            build(
                telegram_gateway_url="https://gateway.example.com",
                alert_destination="operator",
            )
        assert "TELEGRAM_GATEWAY_SCOPE" in str(refused.value)

    def test_a_configured_gateway_is_whole(self) -> None:
        settings = build(
            telegram_gateway_url="http://127.0.0.1:8100/", alert_destination="operator"
        )
        assert settings.alerts_configured is True
        assert settings.telegram_gateway_url == "http://127.0.0.1:8100"
