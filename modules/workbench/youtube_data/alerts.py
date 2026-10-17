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
import re
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
# A title, a channel name and an instrument name come from strangers and carry no length of their own.
LINE_CHARS = 300

PURPOSE = "youtube.film"
PURPOSE_DESCRIPTION = "A film the model read, by the channel's or topic's alert rule"


def slug(text: str) -> str:
    """A name as one segment of a purpose: lowercase letters, digits, `_` and `-`; the rest becomes a dash."""
    cleaned = re.sub(r"[^a-z0-9_-]+", "-", text.lower()).strip("-_")[:60]
    return cleaned or "unknown"


def purpose_for(video) -> str:
    """One purpose for the archive, one segment for the channel: an assignment can move every film or a single channel."""
    return f"{PURPOSE}.{slug(video.channel_title)}"


ARROWS = {"bullish": "▲", "bearish": "▼", "neutral": "▬"}


class GatewayRefused(Exception):
    """The gateway answered, and the answer was a refusal — an unknown destination, a rate limit, a recipient who blocked
    the bot. Never read as "delivered"."""


class GatewayUnreachable(Exception):
    """The gateway did not answer at all."""


class GatewayUnassigned(Exception):
    """Nobody receives this purpose yet. Not a failure and never read as "delivered": the film keeps no marker, so it is
    announced the pass after somebody is assigned - unless the window has let it go as quiet first."""

    def __init__(self, purpose: str) -> None:
        super().__init__(f"nobody receives {purpose!r}")
        self.purpose = purpose


class Gateway:
    """The two routes this package calls on the door to Telegram: send under a purpose, and announce one. The client is
    the host's, over the door's application in this process, so its refusals and its caller record read here exactly as
    they did over HTTP."""

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
        """Tells the door this purpose exists, so the terminal lists it before the first event. Best effort."""
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
        _clip(f"Wpływ {reading['impact_score']}/10 — {video.channel_title}", LINE_CHARS),
        _clip(video.title, LINE_CHARS),
    ]
    # Either half may be the simulation's: a real model reading a simulated film is still a film that does not exist.
    if item.simulated or video.simulated:
        head.insert(0, "[SYMULACJA — ten film nie istnieje]")

    views = [
        f"{_clip(view['name'], 60)} {ARROWS.get(view['sentiment'], '▬')} ({view['conviction']}/5, {view['horizon']})"
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


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


class Alerts:
    """The pass that says what is worth saying. Runs after the readings in the same round, because a film is only a
    candidate once a model has read it."""

    def __init__(
        self,
        pool,
        gateway: Gateway,
        *,
        min_score: int,
        batch_limit: int,
        window: timedelta,
    ) -> None:
        self._pool = pool
        self._gateway = gateway
        # What the door last said: nobody receives these films. `/state` reports it.
        self.unheard = False
        self._min_score = min_score
        self._limit = batch_limit
        self._window = window

    @property
    def telling(self) -> bool:
        return not self.unheard

    async def announce_purposes(self) -> None:
        await self._gateway.describe(PURPOSE, PURPOSE_DESCRIPTION)

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
        heard = False
        for item in waiting:
            if not self._wanted(item):
                async with self._pool.acquire() as conn:
                    await store.set_outcome(conn, item.video.video_id, "quiet")
                continue
            try:
                await self._gateway.send(purpose=purpose_for(item.video), text=message(item))
            except GatewayUnassigned as err:
                self.unheard = True
                log.info("film %s waits: %s", item.video.video_id, err)
                continue
            except (GatewayRefused, GatewayUnreachable) as err:
                # No marker, so the next pass tries again. Named at warning rather than swallowed: a gateway refusing
                # everything is a silence the operator has to be able to find.
                log.warning("could not announce %s: %s", item.video.video_id, err)
                continue
            heard = True
            async with self._pool.acquire() as conn:
                await store.set_outcome(conn, item.video.video_id, "notified", at=datetime.now(UTC))
            sent += 1
        if heard:
            self.unheard = False
        return sent


def build(pool, settings: Settings, gateway: httpx.AsyncClient | None) -> Alerts | None:
    """The alerting this deployment is configured for, or `None`.

    `None` only where there is no door to Telegram at all. With a door, who hears what is the operator's to assign, and a
    purpose nobody hears is reported by `/state` rather than refused at start."""
    if gateway is None:
        log.info("no door to telegram — films will be read and nobody told")
        return None
    return Alerts(
        pool,
        Gateway(gateway),
        min_score=settings.alert_min_impact_score,
        batch_limit=settings.announce_batch_limit,
        window=timedelta(hours=settings.alert_window_hours),
    )
