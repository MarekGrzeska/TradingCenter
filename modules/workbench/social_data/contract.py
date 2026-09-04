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
