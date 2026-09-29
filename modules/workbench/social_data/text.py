"""Feed text as text: what both the post archive and the news do to a document's markup."""

from __future__ import annotations

import html
import re

_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"[ \t]*\n[ \t]*")


def clean(raw: str) -> str:
    """The item's description as text: tags dropped, entities resolved.

    Unescaping is the half the source application skipped, so every `&amp;` reached the screen and
    the model as five characters. Done after the tags go, or an entity-encoded `&lt;b&gt;` would
    turn into a tag nobody stripped.
    """
    return _WHITESPACE.sub("\n", html.unescape(_TAG.sub("", raw))).strip()
