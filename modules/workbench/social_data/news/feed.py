"""RSS 2.0 and Atom, read into `FeedItem`s. `defusedxml` for the reason the Truth Social provider uses it: a
feed is somebody else's document, and an entity expansion is a memory exhaustion performed on ourselves."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from defusedxml.ElementTree import fromstring

from ..text import clean
from .models import FeedItem

log = logging.getLogger(__name__)

ATOM = "{http://www.w3.org/2005/Atom}"
DC = "{http://purl.org/dc/elements/1.1/}"

# Axios sends ~2 KB of body per item; a headline's lead is what a screen needs, not the article.
SUMMARY_LIMIT = 1000


class Unreadable(Exception):
    """A document that is neither RSS nor Atom, or not XML at all."""


def moment(raw: str | None) -> datetime | None:
    """RFC 822 (RSS) or ISO 8601 (Atom, Dublin Core), as UTC. `None` rather than a guess."""
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _summary(raw: str | None, title: str) -> str:
    text = clean(raw or "")
    # Google News repeats the headline and the publisher as the description; a lead saying the title
    # again is noise on every card.
    if not text or text.startswith(title):
        return ""
    return text if len(text) <= SUMMARY_LIMIT else text[: SUMMARY_LIMIT - 1].rstrip() + "…"


def _aggregated_title(title: str, publisher: str) -> str:
    """Google News writes "Headline - Publisher"; the publisher is a field of its own here."""
    suffix = f" - {publisher}"
    return title.removesuffix(suffix)


def _rss_item(item, default_publisher: str) -> FeedItem | None:
    title = clean(item.findtext("title") or "")
    link = (item.findtext("link") or "").strip() or None
    external_id = (item.findtext("guid") or "").strip() or link
    if not title or not external_id:
        return None
    publisher = (item.findtext("source") or "").strip() or default_publisher
    if publisher != default_publisher:
        title = _aggregated_title(title, publisher)
    return FeedItem(
        external_id=external_id,
        title=title,
        publisher=publisher,
        summary=_summary(item.findtext("description"), title),
        url=link,
        published_at=moment(item.findtext("pubDate") or item.findtext(f"{DC}date")),
    )


def _atom_entry(entry, default_publisher: str) -> FeedItem | None:
    title = clean(entry.findtext(f"{ATOM}title") or "")
    link = None
    for candidate in entry.findall(f"{ATOM}link"):
        if candidate.get("rel", "alternate") == "alternate" and candidate.get("href"):
            link = candidate.get("href").strip()
            break
    external_id = (entry.findtext(f"{ATOM}id") or "").strip() or link
    if not title or not external_id:
        return None
    raw_summary = entry.findtext(f"{ATOM}summary") or entry.findtext(f"{ATOM}content")
    return FeedItem(
        external_id=external_id,
        title=title,
        publisher=default_publisher,
        summary=_summary(raw_summary, title),
        url=link,
        published_at=moment(entry.findtext(f"{ATOM}published") or entry.findtext(f"{ATOM}updated")),
    )


def items_from(document: bytes | str, *, publisher: str) -> list[FeedItem]:
    """Every readable item. One without a title or any identifier is dropped: identity is what keeps a
    headline from being stored twice, and a guessed one would do exactly that."""
    try:
        root = fromstring(document)
    except Exception as err:  # every parse failure is the same fact here: unreadable
        raise Unreadable(f"not an XML document: {err}") from err

    if root.tag == "rss" or root.find("channel") is not None:
        found = [_rss_item(item, publisher) for item in root.iter("item")]
    elif root.tag == f"{ATOM}feed":
        found = [_atom_entry(entry, publisher) for entry in root.iter(f"{ATOM}entry")]
    else:
        raise Unreadable(f"neither RSS nor Atom: the document is <{root.tag}>")

    items = [item for item in found if item is not None]
    if len(items) < len(found):
        log.info("%d feed items dropped: no title or no identifier", len(found) - len(items))
    return items
