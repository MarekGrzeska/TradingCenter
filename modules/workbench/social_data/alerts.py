"""Telling the operator about a post worth waking them for.

Two rules shape this file, and both come from the gateway keeping no history of what it sent. The
marker is written **after** a success, never before — so a failed delivery leaves the post waiting
and the next collection pass tries again, which is the whole retry mechanism this system has. And a
post with no reading is never announced: an absent score is not a low one, and "just in case" would
turn the threshold into its opposite exactly where this module knows least.

The price is named rather than hidden: a delivery that succeeded and whose marker did not get
written announces the post a second time. A repeated notification is cheaper than a lost one, and
the other choice would need the gateway to remember messages.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

import httpx

from . import store
from .models import Post

log = logging.getLogger(__name__)

# How many posts one pass may announce. A day that produces forty alerts is a day the operator
# stops reading them, and the rest are still there on the next pass.
BATCH_LIMIT = 10

# Telegram's own ceiling is 4096 and the gateway refuses rather than truncating, so the excerpt is
# cut here — where the cut can be marked as one.
EXCERPT_CHARS = 900


class GatewayRefused(Exception):
    """The gateway answered, and the answer was a refusal — an unknown destination, a rate limit,
    a recipient who blocked the bot. Never read as "delivered"."""


class GatewayUnreachable(Exception):
    """The gateway did not answer at all."""


class GatewayUnassigned(Exception):
    """Nobody receives this purpose yet. Not a failure and never read as "delivered": the marker stays unset, so the
    first pass after the operator assigns it says what is waiting."""

    def __init__(self, purpose: str) -> None:
        super().__init__(f"nobody receives {purpose!r}")
        self.purpose = purpose



class Gateway:
    """The two routes this package calls on the door to Telegram: send under a purpose, and announce one.

    It does not choose who hears: the operator's assignments do, in the terminal. The client is the host's, over the
    door's application in this process, so its refusals and its caller record read here exactly as they did over HTTP."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def send(self, *, purpose: str, text: str) -> None:
        try:
            response = await self._client.post("/messages", json={"purpose": purpose, "text": text})
        except httpx.RequestError as err:
            raise GatewayUnreachable(f"the gateway did not answer: {err}") from err
        if response.is_error:
            if _nobody_listens(response):
                raise GatewayUnassigned(purpose)
            raise GatewayRefused(f"the gateway refused: {_detail(response)}")

    async def describe(self, purpose: str, description: str) -> None:
        """Tells the door this purpose exists, so the terminal lists it before the first event. Best effort: a door
        that cannot be reached now learns it from the first message."""
        try:
            await self._client.put(f"/purposes/{purpose}", json={"description": description})
        except httpx.RequestError as err:
            log.info("could not announce the purpose %s: %s", purpose, err)


def _nobody_listens(response: httpx.Response) -> bool:
    """The door's own code for a purpose with no recipient — not a fault, and not to be read as a refusal."""
    try:
        body = response.json()
    except ValueError:
        return False
    detail = body.get("detail") if isinstance(body, dict) else None
    return response.status_code == 409 and isinstance(detail, dict) and detail.get("code") == "unassigned"


def _detail(response: httpx.Response) -> str:
    """The gateway's own words, kept whole — they carry the wait on a rate limit and the reason on
    a block, which is what makes this log worth reading."""
    try:
        body = response.json()
    except ValueError:
        return response.text.strip() or response.reason_phrase
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, dict):
        return str(detail.get("detail") or detail)
    return str(detail or body)


def slug(text: str) -> str:
    """A name as one segment of a purpose: lowercase letters, digits, `_` and `-`. Whatever else it holds becomes a
    dash, and a name with nothing usable in it is still a segment."""
    cleaned = re.sub(r"[^a-z0-9_-]+", "-", text.lower()).strip("-_")[:60]
    return cleaned or "unknown"


PURPOSE = "social.post"
PURPOSE_DESCRIPTION = "A post the model scored at or above the threshold"


def purpose_for(post: Post) -> str:
    """Where a post is announced: one purpose for the archive, one segment for who wrote it, so an assignment can move
    all of them or a single author."""
    return f"{PURPOSE}.{slug(post.author)}"


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
    """The pass that says what is worth saying. Runs after enrichment in the same round, because a
    post is only a candidate once a model has read it."""

    def __init__(
        self,
        pool,
        gateway: Gateway,
        *,
        min_score: int,
        batch_limit: int = BATCH_LIMIT,
    ) -> None:
        self._pool = pool
        self._gateway = gateway
        self._min_score = min_score
        self._limit = batch_limit
        # What the door last said: nobody receives these posts. `/state` reports it, so that a silent archive can be
        # told from one with nothing to say.
        self.unheard = False

    @property
    def telling(self) -> bool:
        return not self.unheard

    async def announce_purposes(self) -> None:
        await self._gateway.describe(PURPOSE, PURPOSE_DESCRIPTION)

    async def run(self, since: datetime) -> int:
        """How many posts were announced this pass. One failure costs that post only — and costs it
        nothing permanent, because the post keeps no marker and comes back next round."""
        async with self._pool.acquire() as conn:
            waiting = await store.posts_awaiting_notification(
                conn, since=since, min_score=self._min_score, limit=self._limit
            )
        sent = 0
        heard = False
        for post in waiting:
            try:
                await self._gateway.send(purpose=purpose_for(post), text=message(post))
            except GatewayUnassigned as err:
                # Nobody listens to this author yet: not a fault, and no marker, so it is announced the pass after
                # somebody is assigned (within the window and the batch limit).
                self.unheard = True
                log.info("post %s waits: %s", post.id, err)
                continue
            except (GatewayRefused, GatewayUnreachable) as err:
                # No marker, so the next pass tries again. Named at warning rather than swallowed:
                # a gateway refusing everything is a silence the operator has to be able to find.
                log.warning("could not announce post %s: %s", post.id, err)
                continue
            heard = True
            async with self._pool.acquire() as conn:
                await store.mark_notified(conn, post.id, at=datetime.now(UTC))
            sent += 1
        if heard:
            self.unheard = False
        return sent


def build(pool, settings, gateway: httpx.AsyncClient | None) -> Alerts | None:
    """The alerting this deployment is configured for, or `None`.

    `None` only where there is no door to Telegram at all (standalone, or a host that did not hand one in). With a door,
    who hears what is the operator's to assign, so there is nothing here to configure — and a purpose nobody hears is
    reported by `/state` rather than refused at start."""
    if gateway is None:
        log.info("no door to telegram — posts will be collected and nobody told")
        return None
    return Alerts(pool, Gateway(gateway), min_score=settings.alert_min_impact_score)
