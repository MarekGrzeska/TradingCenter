"""The refusals that keep a misconfigured process from starting — and the one absence that is not a
misconfiguration at all."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from telegram_gateway.config import Settings

LOCAL = "postgresql://telegram:change-me@127.0.0.1:55432/telegram"
REMOTE = "postgresql://psql.example.net:5432/telegram?sslmode=require"


def settings(**overrides) -> Settings:
    return Settings(database_url=overrides.pop("database_url", LOCAL), _env_file=None, **overrides)


class TestTheAccountSession:
    def test_all_three_absent_is_a_working_configuration(self) -> None:
        """The module sends without them and refuses only to create bots. Treating this as a
        configuration error would make a credential to a personal account a condition of starting."""
        assert settings().can_create_bots is False

    def test_all_three_present_enables_creating(self) -> None:
        configured = settings(
            telegram_api_id=12345, telegram_api_hash="hash", telegram_session="session"
        )

        assert configured.can_create_bots is True

    @pytest.mark.parametrize(
        "given",
        [
            {"telegram_api_id": 12345},
            {"telegram_api_hash": "hash"},
            {"telegram_api_id": 12345, "telegram_session": "session"},
        ],
    )
    def test_a_partial_session_is_refused_at_startup(self, given: dict) -> None:
        """Two of the three looks configured and fails at the moment the operator asks for a bot,
        pointing at a variable nobody remembers leaving blank."""
        with pytest.raises(ValidationError, match="together or not at all"):
            settings(**given)

    def test_a_blank_line_reads_as_absent(self) -> None:
        """`TELEGRAM_SESSION=` left in a .env is the same intent as the line being gone."""
        assert settings(telegram_api_hash="", telegram_session="  ").can_create_bots is False


class TestTheDatabaseConnection:
    def test_a_remote_database_without_an_identity_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="only connects to a database on this machine"):
            settings(database_url="postgresql://psql.example.net:5432/telegram")

    def test_an_identity_without_tls_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="MUST be encrypted"):
            settings(
                database_url="postgresql://psql.example.net:5432/telegram",
                database_user="app",
            )

    def test_a_credential_in_the_url_is_refused_in_identity_mode(self) -> None:
        """It is not read, so leaving it there is a secret published for nothing."""
        with pytest.raises(ValidationError, match="carries a username or password"):
            settings(
                database_url="postgresql://u:p@psql.example.net:5432/telegram?sslmode=require",
                database_user="app",
            )

    def test_identity_mode_over_tls_is_accepted(self) -> None:
        assert settings(database_url=REMOTE, database_user="app").database_user == "app"


class TestTheCallerLists:
    def test_the_two_lists_are_read_apart(self) -> None:
        configured = settings(
            tool_caller_application_ids="a, b",
            rest_caller_application_ids="c",
        )

        assert configured.tool_caller_ids == {"a", "b"}
        assert configured.rest_caller_ids == {"c"}

    def test_an_empty_list_names_nobody(self) -> None:
        assert settings(tool_caller_application_ids=" , ").tool_caller_ids == frozenset()


class TestTheCeilings:
    @pytest.mark.parametrize(
        "field", ["max_bots", "max_message_chars", "database_pool_size"]
    )
    def test_a_ceiling_below_one_is_refused(self, field: str) -> None:
        with pytest.raises(ValidationError, match="must be at least 1"):
            settings(**{field: 0})

    def test_the_pool_is_smaller_than_the_default(self) -> None:
        """Seven logical databases share one burstable server whose `max_connections` is 35. A
        seventh pool of ten would be the change that makes every module's read wait."""
        assert settings().database_pool_size < 10
