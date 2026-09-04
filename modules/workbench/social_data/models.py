"""What the archive holds, as this module's own shapes. A post arrives as `RawPost` — what a source
could see — and comes back as `Post`, which also carries whatever a model has since made of it."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


@dataclass(frozen=True, slots=True)
class RawPost:
    """One post as a source hands it over: no identifier of ours, no reading, nothing enriched.

    `source` and `external_id` together are the identity — a source numbering its posts the same
    way as another is a collision waiting rather than a hypothetical.
    """

    source: str
    external_id: str
    author: str
    content: str
    published_at: datetime
    url: str | None = None
    is_repost: bool = False


@dataclass(frozen=True, slots=True)
class Post:
    """A stored post and its one current reading. Every reading field is optional together with its
    stamp: a model that has not seen this post leaves all of them empty, which is a normal state."""

    id: int
    source: str
    external_id: str
    author: str
    content: str
    published_at: datetime
    fetched_at: datetime
    url: str | None = None
    is_repost: bool = False
    translated_content: str | None = None
    translated_model: str | None = None
    translated_at: datetime | None = None
    topics: tuple[str, ...] = ()
    impact_score: int | None = None
    analysed_model: str | None = None
    analysed_at: datetime | None = None

    @property
    def analysed(self) -> bool:
        return self.impact_score is not None


class Operation(str, Enum):
    """What a model was asked to do, and what the bill for it is filed under."""

    TRANSLATION = "translation"
    ANALYSIS = "analysis"


@dataclass(frozen=True, slots=True)
class Usage:
    """One call to a model, priced. Kept when the reading it produced is overwritten."""

    post_id: int
    operation: Operation
    model: str
    input_tokens: int
    output_tokens: int
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SourceState:
    """What collection is doing for one source. Without `last_success_at` a quiet day and a source
    that has been unreachable for three hours are the same empty list."""

    source: str
    collecting_since: datetime
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_failure_reason: str | None = None
    consecutive_failures: int = 0
