"""The four tools this module serves at `/mcp` — reduced for a model rather than for a screen.

Three questions and a state: what has been said lately, what was said in a window, what one post
actually says, and whether the archive is still hearing anything."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from .. import store, views
from ._shared import READ_ONLY, Age, PostDetail, PostSummary, ToolContext, excerpt

# The most posts one call returns. A model choosing between forty is already choosing badly, and
# every one of them is paid for by the token.
MAX_POSTS = 50


class SourceStatus(BaseModel):
    source: str
    collecting_since: datetime = Field(
        description="nothing published before this moment is in the archive — there is no backfill"
    )
    last_collection: Age | None = Field(
        default=None, description="the last pass that reached this source, and how long ago"
    )
    stale: bool = Field(
        description="the archive has not heard from this source for several intervals; say so "
        "rather than reporting that nothing was posted"
    )
    last_failure_reason: str | None = None


class ArchiveStatus(BaseModel):
    sources: list[SourceStatus]
    posts_in_window: int
    window_hours: int
    readings_configured: bool = Field(
        description="false means no model is configured, so impact_score and topics are empty by "
        "configuration — not because nothing was worth reading"
    )


def _summary(post) -> PostSummary:
    text, truncated = excerpt(post.content)
    return PostSummary(
        source=post.source,
        external_id=post.external_id,
        author=post.author,
        published_at=post.published_at,
        excerpt=text,
        truncated=truncated,
        is_repost=post.is_repost,
        impact_score=post.impact_score,
        topics=list(post.topics),
        analysed_model=post.analysed_model,
    )


def register(mcp: FastMCP, ctx: ToolContext) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def recent_posts(
        hours: int = 24, min_score: int | None = None, limit: int = 20
    ) -> list[PostSummary]:
        """Posts from the last few hours, newest first — the question asked most of the time.

        `min_score` narrows to what a model already judged market-relevant; it filters a reading
        that exists in the archive, so it costs nothing and is not a fresh judgement.
        """
        end = datetime.now(UTC)
        async with ctx.pool.acquire() as conn:
            found = await store.posts_in_window(
                conn,
                start=end - timedelta(hours=max(1, hours)),
                end=end,
                min_score=min_score,
                limit=min(limit, MAX_POSTS),
            )
        return [_summary(post) for post in found]

    @mcp.tool(annotations=READ_ONLY)
    async def posts_in_window(
        since: datetime,
        until: datetime | None = None,
        source: str | None = None,
        min_score: int | None = None,
        topic: str | None = None,
        limit: int = 20,
    ) -> list[PostSummary]:
        """Posts published between two moments, newest first, narrowed by source, score or topic.

        `topic` matches a topic a model wrote, exactly — the vocabulary is the model's, so
        `recent_posts` first and a topic from what came back is the way to use it.
        """
        end = until or datetime.now(UTC)
        async with ctx.pool.acquire() as conn:
            found = await store.posts_in_window(
                conn,
                start=since,
                end=end,
                source=source,
                min_score=min_score,
                topic=topic,
                limit=min(limit, MAX_POSTS),
            )
        return [_summary(post) for post in found]

    @mcp.tool(annotations=READ_ONLY)
    async def read_post(
        source: str, external_id: str, translated: bool = False
    ) -> PostDetail | dict:
        """One post in full, by the pair naming it. `translated` asks for the Polish reading too."""
        async with ctx.pool.acquire() as conn:
            post = await store.post_by_external_id(conn, source, external_id)
        if post is None:
            # A refusal that says so, not an empty answer: nothing collected and a tool that
            # failed look the same to a model when the answer is nothing at all.
            return {
                "refused": f"no post {external_id!r} from {source!r} is in this archive",
                "do_first": (
                    "recent_posts or posts_in_window lists what is here, with the pair that "
                    "names each one; social_archive_status says how far back the archive goes"
                ),
            }
        return PostDetail(
            source=post.source,
            external_id=post.external_id,
            author=post.author,
            published_at=post.published_at,
            content=post.content,
            translated_content=post.translated_content if translated else None,
            url=post.url,
            is_repost=post.is_repost,
            impact_score=post.impact_score,
            topics=list(post.topics),
            analysed_model=post.analysed_model,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def social_archive_status() -> ArchiveStatus:
        """What the archive is doing — read this before reporting that nobody posted anything.

        An empty window means one of three things: a quiet day, a source this archive has not
        heard from in hours, or a window before collection started. Only this tool tells them apart.
        """
        settings = ctx.settings
        now = datetime.now(UTC)
        async with ctx.pool.acquire() as conn:
            states = await store.collection_states(conn)
            counted = await store.count_in_window(
                conn, start=now - timedelta(hours=settings.collect_window_hours), end=now
            )
        return ArchiveStatus(
            sources=[
                SourceStatus(
                    source=state.source,
                    collecting_since=state.collecting_since,
                    last_collection=Age.of(state.last_success_at),
                    stale=views.is_stale(
                        state,
                        interval_seconds=settings.collect_interval_seconds,
                        after_ticks=settings.stale_after_ticks,
                        now=now,
                    ),
                    last_failure_reason=state.last_failure_reason,
                )
                for state in states
            ],
            posts_in_window=counted,
            window_hours=settings.collect_window_hours,
            readings_configured=settings.model_configured,
        )
