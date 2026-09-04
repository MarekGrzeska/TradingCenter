"""The one source this module has today: Truth Social, read through the public mirror's feed.

The mirror is somebody's side project rather than a documented API — which is why the address is a
setting, why the parser is tested against a saved document, and why an unreadable answer is its own
kind of failure rather than an empty day."""

from __future__ import annotations

import html
import logging
import re
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime

import httpx
from defusedxml.ElementTree import fromstring

from ..models import RawPost
from . import SourceUnreachable, SourceUnreadable

log = logging.getLogger(__name__)

SOURCE = "truth_social"

# The feed carries one person's statements and names them nowhere in the item, so the author is the
# feed's own identity rather than a field read off it.
AUTHOR = "realDonaldTrump"

# What the mirror marks a passed-on post with. Text matching, because the document has no field for
# it — the flag is descriptive and steers nothing, so a miss costs a badge and no data.
_REPOST_MARKERS = ("RT by", "Retruthed", "ReTruth")

_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"[ \t]*\n[ \t]*")


def clean(raw: str) -> str:
    """The item's description as text: tags dropped, entities resolved.

    Unescaping is the half the source application skipped, so every `&amp;` reached the screen and
    the model as five characters. Done after the tags go, or an entity-encoded `&lt;b&gt;` would
    turn into a tag nobody stripped.
    """
    return _WHITESPACE.sub("\n", html.unescape(_TAG.sub("", raw))).strip()


def published_at(raw: str | None) -> datetime | None:
    """The item's date as an instant in UTC, or `None` for one that cannot be read."""
    if not raw:
        return None
    try:
        moment = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    return moment.astimezone(UTC) if moment.tzinfo else moment.replace(tzinfo=UTC)


def posts_from(document: str) -> list[RawPost]:
    """Every readable item in the feed. An item without an identifier or a date is dropped rather
    than stored under a guess: identity is what deduplication rests on."""
    try:
        root = fromstring(document)
    except Exception as err:  # every parse failure is the same fact here: unreadable
        raise SourceUnreadable(f"the feed is not a document this module can read: {err}") from err

    posts: list[RawPost] = []
    for item in root.iter("item"):
        external_id = (item.findtext("guid") or "").strip()
        moment = published_at(item.findtext("pubDate"))
        if not external_id or moment is None:
            log.warning("feed item dropped: no identifier or no readable date")
            continue
        description = item.findtext("description") or ""
        posts.append(
            RawPost(
                source=SOURCE,
                external_id=external_id,
                author=AUTHOR,
                content=clean(description),
                published_at=moment,
                url=(item.findtext("link") or "").strip() or None,
                is_repost=any(marker in description for marker in _REPOST_MARKERS),
            )
        )
    return posts


class TruthSocialFeed:
    """The source, over one HTTP client this module owns."""

    def __init__(self, client: httpx.AsyncClient, *, feed_url: str) -> None:
        self._client = client
        self._feed_url = feed_url

    @property
    def name(self) -> str:
        return SOURCE

    async def fetch(self, day: date) -> list[RawPost]:
        params = {"start_date": day.isoformat(), "end_date": day.isoformat()}
        try:
            response = await self._client.get(self._feed_url, params=params)
            response.raise_for_status()
        except httpx.HTTPError as err:
            raise SourceUnreachable(f"the feed did not answer for {day}: {err}") from err
        return posts_from(response.text)
