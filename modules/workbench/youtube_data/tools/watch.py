"""The tools that add to what is followed, and the one that looks around at the source's expense. Every one of them adds; none
removes — taking a channel off the list is the operator's, through a route, because the agent that could take one off could
take the one the operator cared about. What the agent can do is bounded by the same ceilings the screen is."""

from __future__ import annotations

from datetime import timedelta
from typing import Literal

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from .. import budget, store, watchlist
from ..contract import ChannelOut, TopicOut
from ..providers.base import SourceError
from ..watchlist import WatchlistRefused
from ._shared import ADDS, MAX_FILMS, SPENDS, ToolContext, refused
from .briefs import ChannelBrief, TopicBrief

ASK_THE_OPERATOR = "ask the operator; only they can take something off the list"


class Found(BaseModel):
    video_id: str
    url: str
    title: str
    channel_title: str
    published_at: str
    duration_seconds: int | None
    live_status: str
    simulated: bool


class Followed(BaseModel):
    channel: ChannelBrief
    created: bool = Field(description="false where the channel was already followed, which is left exactly as it was")


class TopicAdded(BaseModel):
    topic: TopicBrief
    created: bool
    defaults_applied: list[str] = Field(description="which limits came from the settings rather than from this call")


class RuleSet(BaseModel):
    kind: Literal["channel", "topic"]
    ref: str
    alert_rule: str


class Queued(BaseModel):
    video_id: str
    title: str
    created: bool = Field(description="false where the film was already in the archive")
    note: str = "Queued for the loop: it is transcribed and read on a coming pass, not now. read_video shows where it is."


def register(mcp: FastMCP, ctx: ToolContext) -> None:
    @mcp.tool(annotations=SPENDS)
    async def search_youtube(phrase: str, hours: int = 48, limit: int = 10) -> list[Found] | dict:
        """Look for films by phrase, newest first, without following anything. THIS SPENDS the source's daily allowance —
        a search costs a hundred of a YouTube key's ten thousand units — so use it deliberately, not to browse.

        Finds films; it does not read them. To have one read, `analyse_video`; to keep looking, `add_topic`.
        """
        providers, settings = ctx.providers, ctx.settings
        source = providers.source
        ceiling = budget.Ceiling(source.name, source.unit, settings.daily_source_units)
        now = providers.clock.now()
        async with ctx.pool.acquire() as conn:
            left = await budget.remaining(conn, ceiling, day=budget.utc_day(now))
        if left < source.search_cost:
            return refused(
                f"the {source.name} source's day cannot pay for a search ({left} of {settings.daily_source_units} "
                f"{source.unit} left, a search costs {source.search_cost})",
                "it starts again at midnight UTC; recent_videos reads what is already here for nothing",
            )
        try:
            found = await source.search(
                phrase, language="", published_after=now - _hours(hours), limit=min(max(limit, 1), MAX_FILMS)
            )
        except SourceError as err:
            return refused(f"the search did not go through: {err}", "try again later, or recent_videos for what is here")
        finally:
            async with ctx.pool.acquire() as conn:
                await store.add_usage(conn, providers.meter.drain(), day=budget.utc_day(now))
        return [
            Found(
                video_id=film.video_id,
                url=f"https://www.youtube.com/watch?v={film.video_id}",
                title=film.title,
                channel_title=film.channel_title,
                published_at=film.published_at.isoformat(),
                duration_seconds=film.duration_seconds,
                live_status=film.live_status,
                simulated=film.simulated,
            )
            for film in found
        ]

    @mcp.tool(annotations=ADDS)
    async def follow_channel(
        reference: str, alert_rule: Literal["always", "threshold", "never"] = "threshold"
    ) -> Followed | dict:
        """Follow a channel by its `@handle`, its id (UC…) or its address. New films are found, transcribed and read.

        `alert_rule` is who gets told: `always` every film, `threshold` only those a model scores high, `never` nobody.
        Following a channel already followed changes nothing about it. Cannot remove a channel — ask the operator.
        """
        try:
            followed = await watchlist.follow_channel(
                ctx.pool, ctx.providers.source, ctx.settings, reference, added_by="agent", alert_rule=alert_rule
            )
        except WatchlistRefused as err:
            return refused(str(err), ASK_THE_OPERATOR)
        return Followed(channel=ChannelBrief.of(ChannelOut.of(followed.channel)), created=followed.created)

    @mcp.tool(annotations=ADDS)
    async def add_topic(
        phrase: str,
        language: str = "",
        interval_minutes: int | None = None,
        max_videos_per_run: int | None = None,
        alert_rule: Literal["always", "threshold", "never"] = "threshold",
    ) -> TopicAdded | dict:
        """Keep searching YouTube for a phrase, and read the new films it turns up. Each search spends the source's day, so
        leave the limits empty unless there is a reason: the answer says which came from the settings.

        Topics wait where the source cannot search — `youtube_archive_status` says so. Cannot remove a topic.
        """
        try:
            added = await watchlist.add_topic(
                ctx.pool,
                ctx.settings,
                phrase,
                added_by="agent",
                language=language,
                interval_minutes=interval_minutes,
                max_videos_per_run=max_videos_per_run,
                alert_rule=alert_rule,
            )
        except WatchlistRefused as err:
            return refused(str(err), ASK_THE_OPERATOR)
        return TopicAdded(
            topic=TopicBrief.of(TopicOut.of(added.topic)),
            created=added.created,
            defaults_applied=list(added.defaults_applied),
        )

    @mcp.tool(annotations=ADDS)
    async def set_alert_rule(
        kind: Literal["channel", "topic"], ref: str, alert_rule: Literal["always", "threshold", "never"]
    ) -> RuleSet | dict:
        """Change who is told about the films of one channel (`ref` its id) or one topic (`ref` its number)."""
        async with ctx.pool.acquire() as conn:
            if kind == "channel":
                updated = await store.update_channel(conn, ref, alert_rule=alert_rule)
            else:
                topic_id = int(ref) if ref.isascii() and ref.isdigit() and len(ref) < 10 else None
                updated = None if topic_id is None else await store.update_topic(conn, topic_id, alert_rule=alert_rule)
        if updated is None:
            return refused(
                f"no {kind} {ref!r} is on the list", "youtube_archive_status lists the channels and topics with their ids"
            )
        return RuleSet(kind=kind, ref=ref, alert_rule=alert_rule)

    @mcp.tool(annotations=ADDS)
    async def analyse_video(reference: str) -> Queued | dict:
        """Put one film, named by its address or id, in the queue to be transcribed and read. Costs what asking the source
        about it costs — a unit of the day, not a search. Whoever asked is not alerted: they are already looking."""
        try:
            queued = await watchlist.analyse_film(ctx.pool, ctx.providers, ctx.settings, reference)
        except WatchlistRefused as err:
            return refused(str(err), "search_youtube finds films by phrase, and recent_videos lists what is here")
        return Queued(video_id=queued.video_id, title=queued.title, created=queued.created)


def _hours(hours: int) -> timedelta:
    return timedelta(hours=max(1, min(hours, 24 * 30)))
