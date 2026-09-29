"""A headline as a feed hands it over, as it is stored, and the delay it arrived with."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


@dataclass(frozen=True, slots=True)
class FeedItem:
    """One item as the feed gives it: no moment of ours yet. `published_at` is `None` where the feed
    gave none, or one this module could not read — never a guess."""

    external_id: str
    title: str
    publisher: str
    summary: str = ""
    url: str | None = None
    published_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class NewsItem:
    source: str
    external_id: str
    publisher: str
    title: str
    summary: str
    url: str | None
    published_at: datetime | None
    first_seen_at: datetime
    previous_fetch_at: datetime | None
    kept_at: datetime | None


class Unmeasured(str, Enum):
    """Why a headline has no delay. Each is a different fact, and none of them is zero."""

    NO_PUBLISH_TIME = "no_publish_time"
    FOUND_THERE = "found_there"
    PUBLISH_TIME_IN_FUTURE = "publish_time_in_future"


@dataclass(frozen=True, slots=True)
class Delay:
    """`lower`: how late the feed itself was — the previous fetch did not have it. `upper`: how long the
    operator waited. Their difference is what this archive's own polling cost."""

    lower_seconds: float | None
    upper_seconds: float | None
    unmeasured: Unmeasured | None


@dataclass(frozen=True, slots=True)
class SourceRow:
    source: str
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    last_failure_at: datetime | None
    last_failure: str | None
    newest_published_at: datetime | None
