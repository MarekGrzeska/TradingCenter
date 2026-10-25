"""The tools that add to what is followed, and the one that looks around at the source's expense. Every one of them adds; none
removes — taking a channel off the list is the operator's, through a route, because the agent that could take one off could
take the one the operator cared about. What the agent can do is bounded by the same ceilings the screen is."""

from __future__ import annotations

from datetime import timedelta

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


class Queued(BaseModel):
    video_id: str
    title: str
    created: bool = Field(description="false where the film was already in the archive")
    note: str = (
        "Accepted and being transcribed and read now, in the background: it takes seconds with captions and minutes when "
        "a model has to listen. read_video shows where it is."
    )


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
    async def follow_channel(reference: str, prompt: str | None = None, filter: str | None = None) -> Followed | dict:
        """Follow a channel by its `@handle`, its id (UC…) or its address. New films are found, transcribed and read.

        `prompt` is the name of one of the prompts `youtube_archive_status` lists; without it the seeded one reads. Only the
        operator writes prompts. `filter` says in words which of the channel's new films to process (1-1000 characters);
        their titles and descriptions are judged against it before any is transcribed. Without it every film is processed.
        It is set only when the channel is new here.

        Who is told about its films is the operator's rule, set on their screen. Following a channel already followed
        changes nothing about it. Cannot remove a channel — ask the operator.
        """
        try:
            followed = await watchlist.follow_channel(
                ctx.pool, ctx.providers.source, ctx.settings, reference, added_by="agent", prompt=prompt, filter=filter
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
    ) -> TopicAdded | dict:
        """Keep searching YouTube for a phrase, and offer the operator what it turns up as candidates. Nothing it finds is
        transcribed or read: the operator decides what to follow or analyse. Each search spends the source's day, so leave
        the limits empty unless there is a reason: the answer says which came from the settings. `language` is a two-letter
        ISO 639-1 code such as `pl` or `en` (never a name like "Polish"), or empty for any.

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
            )
        except WatchlistRefused as err:
            return refused(str(err), ASK_THE_OPERATOR)
        return TopicAdded(
            topic=TopicBrief.of(TopicOut.of(added.topic)),
            created=added.created,
            defaults_applied=list(added.defaults_applied),
        )

    @mcp.tool(annotations=ADDS)
    async def analyse_video(reference: str, prompt: str | None = None) -> Queued | dict:
        """Have one film, named by its address or id, transcribed and read now, in the background and ahead of the queue.
        Costs what asking the source about it costs — a unit of the day, not a search — and then what the transcript and
        the reading cost. Whoever asked is not alerted: they are already looking. Ask read_video a little later.

        `prompt` names the prompt that reads a film new to the archive, as in follow_channel; a film already here keeps its own.
        A film its channel's filter turned away is the exception: this overrides the operator's filter for that film, so it
        is transcribed and read — by `prompt`, or else its channel's — and costs as a new one does."""
        try:
            queued = await watchlist.analyse_film(ctx.pool, ctx.providers, ctx.settings, reference, prompt=prompt)
        except WatchlistRefused as err:
            return refused(str(err), "search_youtube finds films by phrase, and recent_videos lists what is here")
        ingest = getattr(ctx.app.state, "ingest", None)  # pyright: ignore[reportAttributeAccessIssue]
        if queued.process and ingest is not None:
            ingest.start_now(queued.video_id)
        return Queued(video_id=queued.video_id, title=queued.title, created=queued.created)


def _hours(hours: int) -> timedelta:
    return timedelta(hours=max(1, min(hours, 24 * 30)))
