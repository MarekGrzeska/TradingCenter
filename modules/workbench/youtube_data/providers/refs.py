"""What an operator or a model types to name a channel or a film, reduced to the identifier YouTube uses. Pure: nothing
here asks anybody anything, so a reference that cannot be resolved is refused before it costs a request."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from .base import UnsupportedReference

CHANNEL_ID = re.compile(r"^UC[0-9A-Za-z_-]{22}$")
VIDEO_ID = re.compile(r"^[0-9A-Za-z_-]{11}$")
HANDLE = re.compile(r"^@[0-9A-Za-z._-]{3,30}$")

_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}


@dataclass(frozen=True, slots=True)
class ChannelRef:
    kind: str  # "id" | "handle"
    value: str


def channel_ref(reference: str) -> ChannelRef:
    """`UC…`, `@name`, or a channel URL in either form. The old `/c/name` and `/user/name` addresses are refused: they
    name a channel through a lookup nobody offers any more, and guessing would follow the wrong one."""
    text = reference.strip()
    if CHANNEL_ID.match(text):
        return ChannelRef("id", text)
    if HANDLE.match(text):
        return ChannelRef("handle", text)

    parsed = urlparse(text if "://" in text else f"https://{text}")
    if (parsed.hostname or "").lower() in _HOSTS:
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0] == "channel" and CHANNEL_ID.match(parts[1]):
            return ChannelRef("id", parts[1])
        if parts and HANDLE.match(parts[0]):
            return ChannelRef("handle", parts[0])
        if parts and parts[0] in {"c", "user"}:
            raise UnsupportedReference(
                f"{reference!r} is an old-style channel address; give the channel's @handle or its "
                "youtube.com/channel/UC… address instead"
            )
    raise UnsupportedReference(
        f"{reference!r} is not a channel: give a channel id (UC…), an @handle or a youtube.com channel address"
    )


def video_id(reference: str) -> str:
    """The film id out of a watch, short, live or youtu.be address, or a bare id."""
    text = reference.strip()
    if VIDEO_ID.match(text):
        return text

    parsed = urlparse(text if "://" in text else f"https://{text}")
    host = (parsed.hostname or "").lower()
    parts = [part for part in parsed.path.split("/") if part]
    candidate: str | None = None
    if host == "youtu.be" and parts:
        candidate = parts[0]
    elif host in _HOSTS:
        if parts and parts[0] == "watch":
            candidate = parse_qs(parsed.query).get("v", [None])[0]
        elif len(parts) >= 2 and parts[0] in {"shorts", "live", "embed"}:
            candidate = parts[1]
    if candidate and VIDEO_ID.match(candidate):
        return candidate
    raise UnsupportedReference(f"{reference!r} is not a YouTube film address or id")


def uploads_playlist(channel_id: str) -> str:
    """Every channel's uploads playlist is its id with `UC` swapped for `UU` — a fact the API documents and a source
    without an API can therefore still use."""
    return "UU" + channel_id[2:]
