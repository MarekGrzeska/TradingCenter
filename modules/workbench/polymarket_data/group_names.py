"""When two group names are one group (the database's rule, migration 0005), and when they are close enough that a
model asks first — only the tools' rule, since "crypto" and "Cryptocurrency" may really be two categories."""

from __future__ import annotations

from collections.abc import Iterable
from difflib import SequenceMatcher

# Below this a shared prefix is a coincidence: "ai" opens "airlines".
_MIN_PREFIX = 4
_MIN_RATIO = 0.8


def clean(name: str) -> str:
    """A name as it is stored: every run of whitespace one space, none at either end."""
    return " ".join(name.split())


def key(name: str) -> str:
    """The spelling-free form, the SQL twin of `store._name_key` — what this calls equal the database refuses twice."""
    return clean(name).lower()


def similar(name: str, existing: Iterable[str]) -> list[str]:
    """Existing names a new one could be a respelling of: words a subset ("Politics", "US politics"), a prefix
    ("crypto", "cryptocurrency") or a few letters apart ("tariff", "tariffs"). Equal by `key` is the same group."""
    wanted = key(name)
    found: list[str] = []
    for candidate in existing:
        other = key(candidate)
        if other != wanted and _close(wanted, other):
            found.append(candidate)
    return found


def _close(a: str, b: str) -> bool:
    shorter, longer = sorted((a, b), key=len)
    if set(shorter.split()) <= set(longer.split()):
        return True
    if len(shorter) >= _MIN_PREFIX and longer.startswith(shorter):
        return True
    return SequenceMatcher(None, a, b).ratio() >= _MIN_RATIO
