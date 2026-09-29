"""Telling the operator about a film worth a phone's buzz.

Two rules come from the gateway keeping no history of what it sent. The marker is written **after** a success, never
before — so a failed delivery leaves the film waiting and the next pass tries again, which is the whole retry mechanism
this system has. And a film with no reading is never announced: only a read film reaches this step, and an absent score is
not a low one.

The price is named rather than hidden: a delivery that succeeded and whose marker did not get written announces the film
twice. A repeated notification is cheaper than a lost one, and the other choice would need the gateway to remember.

Two things are this package's own. What a channel or a topic asked for (`always`, `threshold`, `never`) decides per film,
and a film that could not be announced within a couple of days is let go as quiet rather than announced late in a heap
the day the gateway comes back."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import httpx

from . import store
from .config import Settings

log = logging.getLogger(__name__)

# Telegram's own ceiling is 4096 and the gateway refuses rather than truncating, so the message is cut here — where the cut
# can be marked as one — and a little under.
MESSAGE_CHARS = 3500
SUMMARY_CHARS = 900
MAX_INSTRUMENTS = 6

ARROWS = {"bullish": "▲", "bearish": "▼", "neutral": "▬"}


class GatewayRefused(Exception):
    """The gateway answered, and the answer was a refusal — an unknown destination, a rate limit, a recipient who blocked
    the bot. Never read as "delivered"."""


class GatewayUnreachable(Exception):
    """The gateway did not answer at all."""


class Gateway:
    """The one route this package calls on the door to Telegram. The client is the host's, over the door's application in
    this process, so its refusals and its caller record read here exactly as they did over HTTP."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def send(self, *, destination: str, text: str) -> None:
        try:
            response = await self._client.post("/messages", json={"destination": destination, "text": text})
        except httpx.RequestError as err:
            raise GatewayUnreachable(f"the gateway did not answer: {err}") from err
        if response.is_error:
            raise GatewayRefused(f"the gateway refused: {_detail(response)}")


def _detail(response: httpx.Response) -> str:
    """The gateway's own words, kept whole — they carry the wait on a rate limit and the reason on a block."""
    try:
        body = response.json()
    except ValueError:
        return response.text.strip() or response.reason_phrase
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, dict):
        return str(detail.get("detail") or detail)
    return str(detail or body)


def message(item: store.ToAnnounce, *, limit: int = MESSAGE_CHARS) -> str:
    """One film as the operator reads it on a phone: what it scored, who said it, what they think and where to watch.

    In Polish, because the summary is; a film from a simulation says so on its first line, since nothing else in a
    Telegram message would."""
    video, reading = item.video, item.reading
    head = [
        f"Wpływ {reading['impact_score']}/10 — {video.channel_title}",
        video.title,
    ]
    if item.simulated:
        head.insert(0, "[SYMULACJA — ten film nie istnieje]")

    views = [
        f"{view['name']} {ARROWS.get(view['sentiment'], '▬')} ({view['conviction']}/5, {view['horizon']})"
        for view in reading["instruments"][:MAX_INSTRUMENTS]
    ]
    tail = []
    if views:
        tail += ["", "; ".join(views)]
    tail += ["", f"https://www.youtube.com/watch?v={video.video_id}"]

    summary = " ".join(str(reading["summary_pl"]).split())
    room = min(SUMMARY_CHARS, limit - len("\n".join(head + tail)) - 4)
    if len(summary) > room:
        summary = summary[: max(room, 0)].rstrip() + "…"
    return "\n".join([*head, "", summary, *tail])


class Alerts:
    """The pass that says what is worth saying. Runs after the readings in the same round, because a film is only a
    candidate once a model has read it."""

    def __init__(
        self,
        pool,
        gateway: Gateway,
        *,
        destination: str,
        min_score: int,
        batch_limit: int,
        window: timedelta,
    ) -> None:
        self._pool = pool
        self._gateway = gateway
        self._destination = destination
        self._min_score = min_score
        self._limit = batch_limit
        self._window = window

    def _wanted(self, item: store.ToAnnounce) -> bool:
        rule = item.video.alert_rule
        if rule == "always":
            return True
        if rule == "threshold":
            return int(item.reading["impact_score"]) >= self._min_score
        return False

    async def run(self, now: datetime) -> int:
        """How many films were announced this pass. One failure costs that film only — and nothing permanent, because it
        keeps no marker and comes back next round."""
        async with self._pool.acquire() as conn:
            await store.expire_unannounced(conn, before=now - self._window)
            waiting = await store.analysed_for_alert(conn, limit=self._limit)

        sent = 0
        for item in waiting:
            if not self._wanted(item):
                async with self._pool.acquire() as conn:
                    await store.set_outcome(conn, item.video.video_id, "quiet")
                continue
            try:
                await self._gateway.send(destination=self._destination, text=message(item))
            except (GatewayRefused, GatewayUnreachable) as err:
                # No marker, so the next pass tries again. Named at warning rather than swallowed: a gateway refusing
                # everything is a silence the operator has to be able to find.
                log.warning("could not announce %s: %s", item.video.video_id, err)
                continue
            async with self._pool.acquire() as conn:
                await store.set_outcome(conn, item.video.video_id, "notified", at=datetime.now(UTC))
            sent += 1
        return sent


def build(pool, settings: Settings, gateway: httpx.AsyncClient | None) -> Alerts | None:
    """The alerting this deployment is configured for, or `None`.

    `None` is a supported state, and the reason it is a return value rather than a refusal: without an adresat the package
    discovers, reads and says nothing, which `/state` reports rather than leaving anybody to guess at."""
    if settings.alert_destination is None or gateway is None:
        log.info("no telegram destination is configured — films will be read and nobody told")
        return None
    return Alerts(
        pool,
        Gateway(gateway),
        destination=settings.alert_destination,
        min_score=settings.alert_min_impact_score,
        batch_limit=settings.announce_batch_limit,
        window=timedelta(hours=settings.alert_window_hours),
    )
