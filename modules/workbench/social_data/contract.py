"""What this module answers with — the published shape, and the one place the terminal and pocket
learn what a post is.

Every reading field is present on every post and empty where there is no reading. A field that
vanishes when a model has not run is a field a consumer cannot tell from a contract that moved."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .models import Post, SourceState

SCORE = "what a model made of this post's market impact, 1..10 — 1 is noise, 10 a global event"


class Problem(BaseModel):
    """One refusal shape for every route, so a consumer handles one thing. `cause` names the layer
    that said no: over HTTP a refused request and an empty window otherwise look alike."""

    detail: str
    cause: Literal["module", "source", "request"] = "module"
    retryable: bool = False


class PostOut(BaseModel):
    source: str = Field(description="which source this came from — part of the post's identity")
    external_id: str = Field(description="the identifier that source gave it; unique within it")
    author: str
    content: str = Field(description="the post as text, tags removed and entities resolved")
    url: str | None = Field(default=None, description="where to read it at the source")
    is_repost: bool = Field(
        default=False, description="passed on rather than written; descriptive, steers nothing"
    )
    published_at: datetime
    fetched_at: datetime = Field(description="when this archive first saw it, UTC")
    translated_content: str | None = Field(
        default=None, description="the Polish reading, or null where no model has produced one"
    )
    translated_model: str | None = None
    translated_at: datetime | None = None
    topics: list[str] = Field(
        default_factory=list, description="short topics a model read out of it; empty, never null"
    )
    impact_score: int | None = Field(default=None, description=SCORE)
    analysed_model: str | None = Field(
        default=None,
        description="which model produced the score and topics — the reading is a fact about "
        "what a model said, so it is never published without naming it",
    )
    analysed_at: datetime | None = None

    @classmethod
    def of(cls, post: Post) -> PostOut:
        return cls(
            source=post.source,
            external_id=post.external_id,
            author=post.author,
            content=post.content,
            url=post.url,
            is_repost=post.is_repost,
            published_at=post.published_at,
            fetched_at=post.fetched_at,
            translated_content=post.translated_content,
            translated_model=post.translated_model,
            translated_at=post.translated_at,
            topics=list(post.topics),
            impact_score=post.impact_score,
            analysed_model=post.analysed_model,
            analysed_at=post.analysed_at,
        )


class PostsOut(BaseModel):
    """A window's answer, with the window it answers for — a list whose edges are implicit is one
    the screen has to guess the meaning of."""

    posts: list[PostOut]
    count: int
    window_from: datetime
    window_to: datetime


class SourceStateOut(BaseModel):
    source: str
    collecting_since: datetime = Field(
        description="when this archive started collecting the source — there is no backfill, so "
        "nothing before this moment is here and never will be"
    )
    last_success_at: datetime | None = Field(
        default=None, description="the last pass that reached the source, UTC"
    )
    last_failure_at: datetime | None = None
    last_failure_reason: str | None = None
    consecutive_failures: int = 0
    stale: bool = Field(
        description="the archive has not collected for several intervals; a quiet source and an "
        "unreachable one are the same empty list without this"
    )

    @classmethod
    def of(cls, state: SourceState, *, stale: bool) -> SourceStateOut:
        return cls(
            source=state.source,
            collecting_since=state.collecting_since,
            last_success_at=state.last_success_at,
            last_failure_at=state.last_failure_at,
            last_failure_reason=state.last_failure_reason,
            consecutive_failures=state.consecutive_failures,
            stale=stale,
        )


class StateOut(BaseModel):
    """What the archive is doing. Read by both screens before they say "no posts"."""

    sources: list[SourceStateOut]
    posts_in_window: int
    window_hours: int
    collect_interval_seconds: int
    model_configured: bool = Field(
        description="whether a model is configured at all — false means readings stay empty by "
        "configuration, not because nothing was worth reading"
    )
    alerts_configured: bool = Field(
        description="whether this archive can notify the operator at all — false means it "
        "collects and says nothing by configuration, which is a supported state"
    )
    alert_min_impact_score: int = Field(
        description="the reading a post needs before it is worth a notification"
    )


DelayUnmeasured = Literal["no_publish_time", "found_there", "publish_time_in_future"]


class NewsItemOut(BaseModel):
    """A headline as the feed gave it, in the feed's language, with the delay it arrived with."""

    source: str = Field(description="which declared feed this came from — part of the identity")
    external_id: str = Field(description="the feed's own identifier for the item, or its link")
    publisher: str = Field(description="who wrote it; for an aggregator, the original publisher")
    title: str
    summary: str = Field(
        description="the lead as text, empty where the feed gave none worth showing"
    )
    content: str = Field(
        description="the body as text where the feed carries more than a lead, paragraphs kept; empty "
        "where it does not — the screen then has only `summary` and the link to the source"
    )
    url: str | None = None
    published_at: datetime | None = Field(
        description="when the feed says it was published; null where it said nothing readable"
    )
    first_seen_at: datetime = Field(description="when this archive first saw it, UTC")
    previous_fetch_at: datetime | None = Field(
        description="the feed's last successful fetch before the one that brought this; null for an "
        "item found there on the feed's first fetch"
    )
    delay_min_seconds: float | None = Field(
        description="the lower bound: how late the feed itself was — its previous fetch did not have it"
    )
    delay_max_seconds: float | None = Field(
        description="the upper bound: how long from publication until this archive saw it"
    )
    delay_unmeasured: DelayUnmeasured | None = Field(
        description="why there is no delay; null exactly when both bounds are present"
    )
    kept_at: datetime | None = Field(
        description="when the operator marked it to keep; a kept headline is never swept"
    )
    expires_at: datetime | None = Field(
        description="when retention will sweep it; null for a kept headline"
    )


class NewsOut(BaseModel):
    items: list[NewsItemOut]
    count: int
    truncated: bool = Field(
        description="the window holds more than this answer carries; the newest are the ones here"
    )
    window_from: datetime | None = Field(description="null when asked for kept headlines only")
    window_to: datetime | None


class NewsSourceOut(BaseModel):
    """One declared feed and its day: is it answering, and how late does what it says reach here."""

    source: str
    publisher: str
    url: str
    interval_seconds: int
    status: Literal["pending", "ok", "failing", "stale"] = Field(
        description="pending: not fetched yet; failing: the latest fetch failed; stale: no success "
        "for several intervals, or ever"
    )
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    last_failure_at: datetime | None
    last_failure: str | None = Field(description="the kind and detail of the last failure")
    newest_published_at: datetime | None = Field(
        description="the newest publication time in the feed at its last successful fetch"
    )
    items_24h: int
    unmeasured_24h: int
    delay_min_median_seconds: float | None
    delay_min_p90_seconds: float | None
    delay_max_median_seconds: float | None
    delay_max_p90_seconds: float | None


class NewsSourcesOut(BaseModel):
    sources: list[NewsSourceOut]
    figures_window_hours: int
    tick_seconds: int
    stale_after_intervals: int
    retention_days: int


class KeepIn(BaseModel):
    """Which headline, and whether to keep it. In the body rather than the path: a feed's identifier is usually a
    URL, and slashes in a path segment are a route that does not match."""

    source: str
    external_id: str
    keep: bool
