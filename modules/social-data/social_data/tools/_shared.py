"""What every tool module here needs, kept out of `__init__.py`."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

# Every tool here. A structural claim an MCP client can act on, not a convention this module
# merely follows: there is nothing on this surface that changes anything.
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)

SCORE = "a model's reading of this post's market impact, 1..10 — 1 is noise, 10 a global event"

# How much of a post a list carries. A day of posts at full length is a context window spent
# before the model has done anything with them; `read_post` is where the rest lives.
EXCERPT_CHARS = 280


@dataclass(frozen=True)
class ToolContext:
    """What a tool needs from the running application, read when the tool is called. Lazily: the surface
    is mounted in `create_app()` while everything it reads is put on `app.state` by the lifespan."""

    app: object

    @property
    def _state(self):
        return self.app.state  # pyright: ignore[reportAttributeAccessIssue]

    @property
    def pool(self):
        return self._state.pool

    @property
    def settings(self):
        return self._state.settings


class Age(BaseModel):
    """A moment and how long ago it was, together. Apart, a model has to do arithmetic on an ISO string
    to know whether an archive is current or stopped on Tuesday."""

    at: datetime
    seconds_ago: float

    @classmethod
    def of(cls, moment: datetime | None) -> Age | None:
        if moment is None:
            return None
        return cls(at=moment, seconds_ago=(datetime.now(UTC) - moment).total_seconds())


def excerpt(text: str) -> tuple[str, bool]:
    """The first part of a post, and whether there is more of it."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= EXCERPT_CHARS:
        return collapsed, False
    return collapsed[:EXCERPT_CHARS].rstrip() + "…", True


class PostSummary(BaseModel):
    """A post as a list carries it: enough to choose one, not enough to read it."""

    source: str = Field(description="pass this and external_id to read_post")
    external_id: str
    author: str
    published_at: datetime
    excerpt: str = Field(description="the opening of the post; truncated when longer")
    truncated: bool = Field(description="true when read_post has more text than this")
    is_repost: bool = False
    impact_score: int | None = Field(default=None, description=SCORE)
    topics: list[str] = Field(default_factory=list)
    analysed_model: str | None = Field(
        default=None,
        description="which model produced the score — null means no model has read this post, "
        "which is not the same as a post it judged unimportant",
    )


class PostDetail(BaseModel):
    """One post in full."""

    source: str
    external_id: str
    author: str
    published_at: datetime
    content: str = Field(description="the post as published, in its own language")
    translated_content: str | None = Field(
        default=None,
        description="the Polish reading, present only when asked for — a model reads the "
        "original without loss, and the translation is for the operator's screen",
    )
    url: str | None = None
    is_repost: bool = False
    impact_score: int | None = Field(default=None, description=SCORE)
    topics: list[str] = Field(default_factory=list)
    analysed_model: str | None = None
