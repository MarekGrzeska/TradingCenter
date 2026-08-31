"""Keeping bot tokens out of the log, including the ones this module never writes.

Telegram puts the token in the request path, so the URL *is* the credential — and `httpx` logs every
request it makes at INFO, URL included. Sanitising this module's own messages is therefore not
enough: the leak arrives through a dependency doing something entirely reasonable.

A filter on the root handlers rather than on one logger, because a filter attached to a logger does
not see records propagating up from its children — and the record to catch is `httpx`'s.
"""

from __future__ import annotations

import logging
import re

# Telegram's own shape: the bot's numeric id, a colon, then 35 characters of secret. Matching the
# shape rather than a known value is what lets this redact a token nobody handed to this filter.
#
# No `\b` before the digits, deliberately: the place a token most needs catching is inside a URL,
# where it is preceded by `/bot` — and `t` to `1` is not a word boundary, so an anchored pattern
# walks straight past the one case this exists for.
_TOKEN = re.compile(r"\d{5,}:[A-Za-z0-9_-]{30,}")

REDACTED = "<token>"


class RedactTokens(logging.Filter):
    """Substitutes, never strips. A blank where a token was reads as a request sent without one,
    which is a different failure from the one being logged."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Rendered first, and the arguments dropped once it is. Inspecting `msg` and `args` apart
        # misses the case that matters: `httpx` passes the URL as an argument, and as an `httpx.URL`
        # rather than a string, so a redactor looking only at strings walks straight past it.
        rendered = record.getMessage()
        if _TOKEN.search(rendered):
            record.msg = _TOKEN.sub(REDACTED, rendered)
            record.args = ()
        return True


# The libraries that are handed a Telegram URL and log it. `httpx` writes one at INFO for every
# request it makes; `httpcore` is named with it because a debug-level connection log carries the same.
EMITTERS = ("httpx", "httpcore")


def install() -> None:
    """Puts the filter on the loggers that can emit a Telegram URL, and on the root handlers.

    On the *loggers* rather than only on handlers, and that is the load-bearing half: a filter runs
    where the record is created, so the mutation survives propagation — while a handler's filters
    live and die with the handler. Under pytest the root handler is replaced between phases, which
    is a small version of the same problem a `dictConfig` reload would cause in production.
    """
    for name in EMITTERS:
        _attach(logging.getLogger(name))
    for handler in logging.getLogger().handlers:
        if not any(isinstance(existing, RedactTokens) for existing in handler.filters):
            handler.addFilter(RedactTokens())


def _attach(logger: logging.Logger) -> None:
    if not any(isinstance(existing, RedactTokens) for existing in logger.filters):
        logger.addFilter(RedactTokens())


def redact(text: str) -> str:
    """The same substitution for a string that is not a log record — a refusal on its way to a caller."""
    return _TOKEN.sub(REDACTED, text)
