"""A message as a template with `{name}` slots. Its own substitution rather than `str.format`: a template is typed into a
browser, and `format` reaches into attributes (`{x.__class__}`) of whatever it is given."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

CONDITION_DEFAULT = "{rule}: {value}"
EVENT_DEFAULT = "{text}"

# A whole message is cut here, where the cut can be marked as one; it is sent in parts, because Telegram accepts a little
# over `PART` in one message and the gateway refuses rather than cuts.
LIMIT = 16_000
PART = 3500
CUT = "…"
_BREAKS = ("\n\n", "\n", " ")

_SLOT = re.compile(r"\{([^{}]*)\}")
_NAME = re.compile(r"[a-z_][a-z0-9_]*")


def slots(template: str) -> list[str]:
    """Every slot the template names, in order."""
    return [found.strip() for found in _SLOT.findall(template)]


def unknown_slots(template: str, allowed: Iterable[str]) -> list[str]:
    """The slots that are not a name this rule can fill — an unknown one is a typo, and would send as an empty string."""
    known = set(allowed)
    return [slot for slot in slots(template) if _NAME.fullmatch(slot) is None or slot not in known]


def render(template: str, values: Mapping[str, Any], *, limit: int = LIMIT) -> str:
    """The template with its slots filled. A slot with no value is empty, and the whole is cut to `limit` with a mark."""

    def fill(found: re.Match[str]) -> str:
        value = values.get(found.group(1).strip())
        return "" if value is None else _text(value)

    text = _SLOT.sub(fill, template).strip()
    if len(text) > limit:
        return text[: limit - len(CUT)].rstrip() + CUT
    return text


def parts(text: str, *, limit: int = PART) -> list[str]:
    """The message as the messages it is sent in, each within `limit`: cut at the last paragraph that fits, else the last
    line, else the last word — a hard cut only for a word longer than a message."""
    found: list[str] = []
    rest = text.strip()
    while len(rest) > limit:
        window = rest[: limit + 1]
        at = next((window.rfind(mark) for mark in _BREAKS if window.rfind(mark) > 0), limit)
        found.append(rest[:at].rstrip())
        rest = rest[at:].lstrip()
    if rest:
        found.append(rest)
    return found


def _text(value: Any) -> str:
    if isinstance(value, bool):
        return "tak" if value else "nie"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, list):
        return ", ".join(_text(one) for one in value)
    return str(value)
