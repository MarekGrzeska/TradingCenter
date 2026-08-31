"""The filter that keeps bot tokens out of the log. Its own tests, at the level it works at — the
integration test in `test_sending.py` only proves the pairing with `httpx` is real."""

from __future__ import annotations

import logging

import pytest

from telegram_gateway.redaction import REDACTED, RedactTokens, redact

TOKEN = "123456:AAHveryveryverysecretveryverysecre1"


def record(msg, *args) -> logging.LogRecord:
    return logging.LogRecord("test", logging.INFO, __file__, 1, msg, args, None)


class TestWhatItCatches:
    def test_a_token_inside_a_url_is_caught(self) -> None:
        """The case the filter exists for, and the one an anchored pattern misses: in a URL the token
        is preceded by `/bot`, and `t` to `1` is not a word boundary."""
        assert TOKEN not in redact(f"POST https://api.telegram.org/bot{TOKEN}/sendMessage")

    def test_a_token_passed_as_a_non_string_argument_is_caught(self) -> None:
        """`httpx` logs the URL as an `httpx.URL`, so a redactor that only inspects strings walks
        past it. The filter renders the record first and drops the arguments once it has."""

        class Url:
            def __str__(self) -> str:
                return f"https://api.telegram.org/bot{TOKEN}/sendMessage"

        entry = record("HTTP Request: %s %s", "POST", Url())

        RedactTokens().filter(entry)

        assert TOKEN not in entry.getMessage()
        assert REDACTED in entry.getMessage()

    def test_it_substitutes_rather_than_strips(self) -> None:
        """A blank where a token was reads as a request sent without one — a different failure from
        the one being logged."""
        assert redact(f"bot{TOKEN} refused") == f"bot{REDACTED} refused"

    def test_a_record_with_no_token_is_left_with_its_arguments(self) -> None:
        entry = record("sent to %s", "operator")

        RedactTokens().filter(entry)

        assert entry.args == ("operator",)
        assert entry.getMessage() == "sent to operator"


class TestWhatItLeavesAlone:
    @pytest.mark.parametrize(
        "text",
        [
            "12:30:00 the market opened",
            "chat_id: 4242",
            "postgresql://host:5432/telegram",
            "an ordinary sentence with a colon: and some words after it",
        ],
    )
    def test_ordinary_text_is_untouched(self, text: str) -> None:
        """A redactor that fires on anything with a colon would quietly eat the log it is protecting."""
        assert redact(text) == text

    def test_the_filter_never_drops_a_record(self) -> None:
        """It redacts; it does not decide what gets logged. A filter returning False here would lose
        the line that says something went wrong."""
        assert RedactTokens().filter(record(f"bot{TOKEN}")) is True
