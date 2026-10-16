"""The shape of a purpose and the rule that picks a recipient for one — both pure, so both are tested
without a database.

A purpose is a dotted name: `youtube.film.some-channel`. The segments left to right go from the kind of
event to its source, which is what lets an assignment to `youtube.film` catch every channel and one to
`youtube.film.some-channel` move a single one.
"""

from __future__ import annotations

import re

from .errors import InvalidPurpose

DEFAULT_KEY = "*"
MAX_LENGTH = 120

_SEGMENT = r"[a-z0-9][a-z0-9_-]*"
_PURPOSE = re.compile(rf"^{_SEGMENT}(\.{_SEGMENT})*$")

_SHAPE = (
    "lowercase letters, digits, '_' and '-' in non-empty segments separated by '.', "
    f"at most {MAX_LENGTH} characters (for example 'youtube.film.some-channel')"
)


def valid_purpose(name: str) -> str:
    """The name, or a refusal that states the shape."""
    if len(name) > MAX_LENGTH or _PURPOSE.fullmatch(name) is None:
        raise InvalidPurpose(name=name, shape=_SHAPE)
    return name


def valid_key(key: str) -> str:
    """An assignment key: a purpose, a prefix of one, or `*`."""
    return key if key == DEFAULT_KEY else valid_purpose(key)


def candidates(purpose: str) -> list[str]:
    """Every key an assignment could match this purpose by, most specific first, `*` last.

    Prefixes are cut at segment boundaries: `market.price` covers `market.price.eurusd` and not
    `market.prices`.
    """
    parts = purpose.split(".")
    keys = [".".join(parts[:end]) for end in range(len(parts), 0, -1)]
    return [*keys, DEFAULT_KEY]


def deciding_key(purpose: str, keys: set[str] | frozenset[str]) -> str | None:
    """Which of these assignment keys decides the purpose — the same answer `store.recipient_of` gets in
    SQL, for the screens that show every purpose at once and would otherwise ask once per row."""
    return next((key for key in candidates(purpose) if key in keys), None)
