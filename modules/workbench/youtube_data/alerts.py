"""Telling the alerts package about a film the model has read.

This package no longer decides whether a film is worth a phone's buzz, nor whom to buzz: it says that a film was read, with
what the model made of it, and the operator's rules in `/alerts` do the rest. What stays here is the part that has to be
right on this side. A film is handed over **once**; the marker is written only **after** the alerts package has accepted it,
so a refusal leaves the film waiting and the next pass tries again — which is the whole retry mechanism this system has; and
a film with no reading is never handed over, because an absent score is not a low one.

Handing over twice is harmless — the alerts package takes the same film, by its id, as the same event — and a film that could
not be handed over within a couple of days is let go as quiet rather than announced late in a heap the day the package returns."""

from __future__ import annotations

import logging
import re
import time
from datetime import UTC, datetime, timedelta

import httpx

from . import store
from .config import Settings

log = logging.getLogger(__name__)

# Telegram's own ceiling is 4096 and the door refuses rather than truncating, so the message is cut here — where the cut
# can be marked as one — and a little under.
MESSAGE_CHARS = 3500
SULK_SECONDS = 600.0
SUMMARY_CHARS = 900
# A title and a channel name come from strangers and carry no length of their own.
LINE_CHARS = 300

# The one origin that is not a door the archive looks through: a film the operator or the agent named.
MANUAL = "manual"

EVENT_TYPE = "youtube.film.read"
EVENT_DESCRIPTION = "A film the model read, with its impact score and the prompt that read it"
EVENT_SCHEMA = {
    "type": "object",
    "description": "`text` is the ready message: score and channel, the title, the summary in Polish and the link.",
    "properties": {
        "channel": {"type": "string", "x-seen-values": True},
        "channel_slug": {"type": "string"},
        "topic": {"type": "string", "x-seen-values": True},
        "title": {"type": "string"},
        "video_id": {"type": "string"},
        "impact_score": {"type": "integer"},
        "prompt": {"type": "string", "x-seen-values": True},
        "url": {"type": "string"},
        "simulated": {"type": "boolean"},
    },
}


def slug(text: str) -> str:
    """A name as one word of an attribute a rule can match: lowercase letters, digits, `_` and `-`; the rest becomes a dash."""
    cleaned = re.sub(r"[^a-z0-9_-]+", "-", text.lower()).strip("-_")[:60]
    return cleaned or "unknown"


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


def attributes_of(item: store.ToAnnounce) -> dict:
    video, reading = item.video, item.reading
    return {
        "channel": video.channel_title,
        "channel_slug": slug(video.channel_title),
        "topic": item.topic or "",
        "title": video.title,
        "video_id": video.video_id,
        "impact_score": int(reading["impact_score"]),
        "prompt": item.prompt,
        "url": f"https://www.youtube.com/watch?v={video.video_id}",
        "simulated": bool(item.simulated or video.simulated),
    }


def message(item: store.ToAnnounce, *, limit: int = MESSAGE_CHARS) -> str:
    """One film as the operator reads it on a phone: what it scored, who said it, what it says and where to watch.

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

    tail = ["", f"https://www.youtube.com/watch?v={video.video_id}"]

    summary = " ".join(str(reading["summary_pl"]).split())
    room = min(SUMMARY_CHARS, limit - len("\n".join(head + tail)) - 4)
    if len(summary) > room:
        summary = summary[: max(room, 0)].rstrip() + "…"
    return "\n".join([*head, "", summary, *tail])


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


class Alerts:
    """The pass that hands over what was read. Runs after the readings in the same round, because a film is only worth
    handing over once a model has read it."""

    def __init__(self, pool, publisher: Publisher, *, batch_limit: int, window: timedelta) -> None:
        self._pool = pool
        self._publisher = publisher
        self._limit = batch_limit
        self._window = window
        self._announced = False
        # What the alerts package last said: it did not take the films. `/state` reports it.
        self.failing = False
        # A film the alerts package refused is passed over for a while, so a few refused ones cannot hold up every film
        # behind them.
        self._sulking: dict[str, float] = {}

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

    async def run(self, now: datetime) -> int:
        """How many films were handed over this pass. One failure costs that film only — and nothing permanent, because it
        keeps no marker and comes back next round."""
        if not self._announced:
            await self.announce_types()
            if not self._announced:
                self.failing = True
                return 0
        async with self._pool.acquire() as conn:
            await store.expire_unannounced(conn, before=now - self._window)
            clock = time.monotonic()
            self._sulking = {film: until for film, until in self._sulking.items() if until > clock}
            fetched = await store.analysed_for_alert(conn, limit=self._limit + len(self._sulking))
        waiting = [item for item in fetched if item.video.video_id not in self._sulking][: self._limit]

        handed = 0
        failed = False
        for item in waiting:
            if item.video.origins == (MANUAL,):
                # Named by hand: whoever asked is already looking, and a rule about the channel was not asked about this film.
                async with self._pool.acquire() as conn:
                    await store.set_outcome(conn, item.video.video_id, "quiet")
                continue
            try:
                await self._publisher.publish(
                    source_key=item.video.video_id, attributes=attributes_of(item), text=message(item)
                )
            except (Rejected, Unreachable) as err:
                # No marker, so the next pass tries again. Named at warning rather than swallowed: an alerts package
                # refusing everything is a silence the operator has to be able to find.
                log.warning("could not hand over %s: %s", item.video.video_id, err)
                failed = True
                if isinstance(err, Rejected):
                    self._sulking[item.video.video_id] = clock + SULK_SECONDS
                continue
            async with self._pool.acquire() as conn:
                await store.set_outcome(conn, item.video.video_id, "notified", at=datetime.now(UTC))
            handed += 1
        self.failing = failed
        return handed


def build(pool, settings: Settings, alerts: httpx.AsyncClient | None) -> Alerts | None:
    """The hand-over this deployment is configured for, or `None`.

    `None` only where there is no alerts package in the process: films are read and nobody is told, and `/state` says so."""
    if alerts is None:
        log.info("no alerts package — films will be read and nobody told")
        return None
    return Alerts(
        pool,
        Publisher(alerts),
        batch_limit=settings.announce_batch_limit,
        window=timedelta(hours=settings.alert_window_hours),
    )
