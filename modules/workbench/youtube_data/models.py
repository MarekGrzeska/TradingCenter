"""What the archive holds, as this package's own shapes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# A film's life. `discovered` is also "waiting for a transcript". `gave_up` and `skipped` are never picked up again.
DISCOVERED = "discovered"
NO_TRANSCRIPT = "no_transcript"
TRANSCRIBED = "transcribed"
ANALYSED = "analysed"
NOTIFIED = "notified"
QUIET = "quiet"
GAVE_UP = "gave_up"
SKIPPED = "skipped"

STATES = (DISCOVERED, NO_TRANSCRIPT, TRANSCRIBED, ANALYSED, NOTIFIED, QUIET, GAVE_UP, SKIPPED)

ADDED_BY = ("operator", "agent")

# What a model made of a search result by its metadata. `unscreened` is a result nobody could read: no model, no tokens left,
# an answer that broke the schema — proposed all the same, because a candidate costs nothing to look at.
PROPOSED = "proposed"
REJECTED = "rejected"
UNSCREENED = "unscreened"
VERDICTS = (PROPOSED, REJECTED, UNSCREENED)

# What the operator did with a candidate. `None` is not decided yet.
DISMISSED = "dismissed"
ANALYSED_BY_HAND = "analysed"
CHANNEL_FOLLOWED = "channel_followed"
CHANNEL_IGNORED = "channel_ignored"
DECISIONS = (DISMISSED, ANALYSED_BY_HAND, CHANNEL_FOLLOWED, CHANNEL_IGNORED)


@dataclass(frozen=True, slots=True)
class Channel:
    channel_id: str
    title: str
    handle: str | None
    uploads_playlist_id: str | None
    language: str
    prompt_id: int
    active: bool
    added_by: str
    added_at: datetime
    last_discovery_at: datetime | None


@dataclass(frozen=True, slots=True)
class Topic:
    id: int
    phrase: str
    language: str
    interval_minutes: int
    max_videos_per_run: int
    active: bool
    added_by: str
    added_at: datetime
    last_run_at: datetime | None


@dataclass(frozen=True, slots=True)
class Video:
    video_id: str
    channel_id: str | None
    channel_title: str
    title: str
    published_at: datetime
    duration_seconds: int | None
    live_status: str
    origins: tuple[str, ...]
    audio_language: str | None
    prompt_id: int
    state: str
    skip_reason: str | None
    attempts: int
    next_attempt_at: datetime | None
    reading_failures: int
    simulated: bool
    discovered_at: datetime
    notified_at: datetime | None


@dataclass(frozen=True, slots=True)
class Prompt:
    """What the operator tells a model to look for in a film, at its latest version."""

    id: int
    name: str
    seeded: bool
    version: int
    body: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Candidate:
    """A film a topic's search found, not yet in the archive and not to be read unless the operator says so."""

    video_id: str
    topic_id: int | None
    phrase: str
    channel_id: str | None
    channel_title: str
    title: str
    published_at: datetime
    duration_seconds: int | None
    simulated: bool
    found_at: datetime
    verdict: str
    reason: str | None
    screened_by: str | None
    decision: str | None
    decided_at: datetime | None


@dataclass(frozen=True, slots=True)
class IgnoredChannel:
    channel_id: str
    channel_title: str
    ignored_at: datetime


@dataclass(frozen=True, slots=True)
class LoopSettings:
    """What the operator turns: how often the loop passes, and what a topic added without limits of its own gets."""

    poll_interval_minutes: int
    topic_interval_minutes: int
    topic_max_videos: int

    @property
    def poll_interval_seconds(self) -> int:
        return self.poll_interval_minutes * 60
