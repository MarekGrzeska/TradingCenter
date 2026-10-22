"""A message as a template with `{name}` slots. Its own substitution rather than `str.format`: a template is typed into a
browser, and `format` reaches into attributes (`{x.__class__}`) of whatever it is given."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

CONDITION_DEFAULT = "{rule}: {value}"
EVENT_DEFAULT = "{text}"

# What Telegram accepts is a little over this, and the gateway refuses rather than cuts — so it is cut here, where the cut
# can be marked as one.
LIMIT = 3500
CUT = "…"

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


def _text(value: Any) -> str:
    if isinstance(value, bool):
        return "tak" if value else "nie"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, list):
        return ", ".join(_text(one) for one in value)
    return str(value)
