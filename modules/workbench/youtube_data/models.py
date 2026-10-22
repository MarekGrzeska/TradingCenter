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
    prompt_id: int
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
