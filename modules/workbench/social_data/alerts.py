"""Telling the alerts package about a post the model has read.

This package no longer decides whether a post is worth waking anybody for, nor whom: it says that a post was read, with what
the model made of it, and the operator's rules in `/alerts` do the rest. What stays here is the part that has to be right
on this side: a post is handed over **once**, the marker is written only **after** the alerts package has accepted it — so a
refusal leaves the post waiting and the next collection pass tries again, which is the whole retry mechanism — and a post
with no reading is never handed over, because an absent score is not a low one.

Handing over twice is harmless: the alerts package takes the same post, by its id, as the same event.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

import httpx

from . import store
from .models import Post

log = logging.getLogger(__name__)

# How many posts one pass may hand over. The rest are still there on the next pass.
BATCH_LIMIT = 50

# Telegram's own ceiling is 4096 and the door refuses rather than truncating, so the excerpt is cut here — where the cut
# can be marked as one.
EXCERPT_CHARS = 900

EVENT_TYPE = "social.post.read"
EVENT_DESCRIPTION = "A post the model read, with its impact score and topics"
EVENT_SCHEMA = {
    "type": "object",
    "properties": {
        "author": {"type": "string"},
        "author_slug": {"type": "string"},
        "impact_score": {"type": "integer"},
        "topics": {"type": "array", "items": {"type": "string"}},
        "url": {"type": "string"},
        "translated": {"type": "boolean"},
    },
}


class Rejected(Exception):
    """The alerts package answered, and the answer was no. Never read as 'handed over'."""


class Unreachable(Exception):
    """The alerts package did not answer at all."""


class Publisher:
    """The two routes this package calls on the alerts package: announce what it can say, and say it. The client is the
    host's, over the package's application in this process, so its refusals and its caller record read here exactly as they
    would over HTTP."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def announce(self) -> None:
        try:
            response = await self._client.put(
                f"/event-types/{EVENT_TYPE}", json={"description": EVENT_DESCRIPTION, "schema": EVENT_SCHEMA}
            )
        except httpx.RequestError as err:
            raise Unreachable(f"the alerts package did not answer: {err}") from err
        if response.is_error:
            raise Rejected(f"the alerts package refused the announcement: {_detail(response)}")

    async def publish(self, *, source_key: str, attributes: dict, text: str) -> None:
        body = {"type": EVENT_TYPE, "source_key": source_key, "attributes": attributes, "text": text}
        try:
            response = await self._client.post("/events", json=body)
        except httpx.RequestError as err:
            raise Unreachable(f"the alerts package did not answer: {err}") from err
        if response.is_error:
            raise Rejected(f"the alerts package refused the event: {_detail(response)}")


def _detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text.strip() or response.reason_phrase
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, dict):
        return str(detail.get("detail") or detail)
    return str(detail or body)


def slug(text: str) -> str:
    """A name as one word of an attribute a rule can match: lowercase letters, digits, `_` and `-`. Whatever else it holds
    becomes a dash, and a name with nothing usable in it is still a word."""
    cleaned = re.sub(r"[^a-z0-9_-]+", "-", text.lower()).strip("-_")[:60]
    return cleaned or "unknown"


def attributes_of(post: Post) -> dict:
    return {
        "author": post.author,
        "author_slug": slug(post.author),
        "impact_score": post.impact_score,
        "topics": list(post.topics),
        "url": post.url or "",
        "translated": post.translated_content is not None,
    }


def message(post: Post) -> str:
    """One post as the operator reads it on a phone: what it scored, who wrote it, and enough of it
    to decide whether to open the terminal.

    **In Polish where the module has it**, which is the point of translating at collection rather
    than at reading time: the notification is the one place the reading is used with no terminal to
    fall back to. The original stands in when a post was scored but not translated — the two are
    separate readings and either can fail on its own — and the line below says which arrived.
    """
    body = post.translated_content or post.content
    text = " ".join(body.split())
    if len(text) > EXCERPT_CHARS:
        text = text[:EXCERPT_CHARS].rstrip() + "…"
    lines = [
        f"Impact {post.impact_score}/10 — {post.author}",
        "",
        text,
    ]
    if post.translated_content is None:
        # Said rather than left to be inferred: an untranslated post is not an English post the
        # operator asked for, it is a reading that did not arrive.
        lines += ["", "(oryginał — tłumaczenie nie dotarło)"]
    if post.topics:
        lines += ["", ", ".join(post.topics)]
    if post.url:
        lines += ["", post.url]
    return "\n".join(lines)


class Alerts:
    """The pass that hands over what was read. Runs after enrichment in the same round, because a post is only worth handing
    over once a model has read it."""

    def __init__(self, pool, publisher: Publisher, *, batch_limit: int = BATCH_LIMIT) -> None:
        self._pool = pool
        self._publisher = publisher
        self._limit = batch_limit
        self._announced = False
        # What the alerts package last said: it did not take the posts. `/state` reports it.
        self.failing = False

    @property
    def telling(self) -> bool:
        return not self.failing

    async def announce_types(self) -> None:
        """Best effort at start: a package that cannot be reached now learns it from the first pass."""
        try:
            await self._publisher.announce()
            self._announced = True
        except (Rejected, Unreachable) as err:
            log.info("could not announce %s yet: %s", EVENT_TYPE, err)

    async def run(self, since: datetime) -> int:
        """How many posts were handed over this pass. One failure costs that post only — and costs it nothing permanent,
        because the post keeps no marker and comes back next round."""
        if not self._announced:
            await self.announce_types()
            if not self._announced:
                self.failing = True
                return 0
        async with self._pool.acquire() as conn:
            waiting = await store.posts_awaiting_notification(conn, since=since, limit=self._limit)
        handed = 0
        failed = False
        for post in waiting:
            try:
                await self._publisher.publish(source_key=str(post.id), attributes=attributes_of(post), text=message(post))
            except (Rejected, Unreachable) as err:
                # No marker, so the next pass tries again. Named at warning rather than swallowed: an alerts package
                # refusing everything is a silence the operator has to be able to find.
                log.warning("could not hand over post %s: %s", post.id, err)
                failed = True
                continue
            async with self._pool.acquire() as conn:
                await store.mark_notified(conn, post.id, at=datetime.now(UTC))
            handed += 1
        self.failing = failed
        return handed


def build(pool, settings, alerts: httpx.AsyncClient | None) -> Alerts | None:
    """The hand-over this deployment is configured for, or `None`.

    `None` only where there is no alerts package in the process (standalone, or a host that did not hand one in): posts are
    collected and read, and `/state` says nobody is told."""
    if alerts is None:
        log.info("no alerts package — posts will be collected and nobody told")
        return None
    return Alerts(pool, Publisher(alerts))
