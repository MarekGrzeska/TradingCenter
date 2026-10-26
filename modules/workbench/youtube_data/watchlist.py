"""What the operator and the agent may add to the archive: a channel, a topic, one film. The same functions serve the REST
routes and the tools, so a ceiling or a refusal is one rule and not two that agree today.

Everything here refuses with a reason a person can act on, and never with a half-written row: the source is asked first,
the ceiling checked second, and only then is anything stored."""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import budget, loop_settings, prompts, store
from .config import Settings
from .models import ADDED_BY, DISCOVERED, FILTERED_OUT, NO_TRANSCRIPT, TRANSCRIBED, Channel, Topic
from .providers.base import ChannelInfo, SourceError, VideoSource
from .providers.refs import video_id

# A film in these states has no reading yet and may still get one; every other state is an end.
_STILL_ON_ITS_ROAD = (DISCOVERED, NO_TRANSCRIPT, TRANSCRIBED)

MAX_PHRASE_CHARS = 200
_LANGUAGE = re.compile(r"^[a-z]{2}(?:[-_][a-z0-9]+)?$")
MAX_FILTER_CHARS = 1000
MIN_INTERVAL_MINUTES = loop_settings.MIN_INTERVAL_MINUTES
MAX_INTERVAL_MINUTES = loop_settings.MAX_INTERVAL_MINUTES
MAX_VIDEOS_PER_RUN = loop_settings.MAX_VIDEOS_PER_RUN


class WatchlistRefused(Exception):
    """The request cannot be done, and this says why in words meant for whoever asked."""


async def _prompt_id(pool, choice: int | str | None) -> int:
    async with pool.acquire() as conn:
        try:
            return await prompts.resolve(conn, choice)
        except prompts.PromptRefused as err:
            raise WatchlistRefused(str(err)) from err


def clean_filter(filter: str | None) -> str | None:
    """A channel's filter as it will be stored, or `None` for no filter. Blank is a refusal rather than "none": it would read
    as a filter that was set, and judge every film against nothing."""
    if filter is None:
        return None
    text = filter.strip()
    if not text or len(text) > MAX_FILTER_CHARS:
        raise WatchlistRefused(f"a filter is 1 to {MAX_FILTER_CHARS} characters saying which films to process")
    return text


def language_code(language: str) -> str:
    """A language as the YouTube Data API takes it: `pl`, not `Polish` — which it answers with a 400 on every search. A
    regional spelling (`pl-PL`) is narrowed to its language, and empty means any."""
    text = language.strip().lower()
    if not text:
        return ""
    if _LANGUAGE.match(text) is None:
        raise WatchlistRefused(f"a language is a two-letter ISO 639-1 code such as 'pl' or 'en', or empty; got {language!r}")
    return text[:2]


def _check_choice(name: str, value: str, allowed) -> None:
    if value not in allowed:
        raise WatchlistRefused(f"{name} must be one of {', '.join(allowed)}; got {value!r}")


@dataclass(frozen=True, slots=True)
class Followed:
    channel: Channel
    created: bool


async def follow_channel(
    pool,
    source: VideoSource,
    settings: Settings,
    reference: str,
    *,
    added_by: str,
    prompt: int | str | None = None,
    language: str = "",
    filter: str | None = None,
) -> Followed:
    prompt_id = await _prompt_id(pool, prompt)
    _check_choice("added_by", added_by, ADDED_BY)
    language = language_code(language)
    criteria = clean_filter(filter)
    try:
        info: ChannelInfo = await source.resolve_channel(reference)
    except SourceError as err:
        raise WatchlistRefused(str(err)) from err

    async with pool.acquire() as conn:
        existing = await store.get_channel(conn, info.channel_id)
        if existing is not None:
            return Followed(existing, created=False)
        if await store.count_channels(conn) >= settings.max_channels:
            raise WatchlistRefused(
                f"the watch list holds {settings.max_channels} channels, which is its ceiling — ask the operator "
                "to take one off; adding another would need a decision about which"
            )
        channel = await store.add_channel(
            conn, info, language=language, prompt_id=prompt_id, added_by=added_by, filter=criteria
        )
    return Followed(channel, created=True)


@dataclass(frozen=True, slots=True)
class AddedTopic:
    topic: Topic
    created: bool
    # Which of the topic's limits came from the settings rather than from whoever asked, so the answer can say so.
    defaults_applied: tuple[str, ...]


async def add_topic(
    pool,
    settings: Settings,
    phrase: str,
    *,
    added_by: str,
    language: str = "",
    interval_minutes: int | None = None,
    max_videos_per_run: int | None = None,
) -> AddedTopic:
    text = " ".join(phrase.split())
    if not text or len(text) > MAX_PHRASE_CHARS:
        raise WatchlistRefused(f"a topic is a phrase of 1 to {MAX_PHRASE_CHARS} characters")
    _check_choice("added_by", added_by, ADDED_BY)
    language = language_code(language)

    defaults: list[str] = []
    if interval_minutes is None or max_videos_per_run is None:
        async with pool.acquire() as conn:
            standing = await loop_settings.current(conn, settings)
        if interval_minutes is None:
            interval_minutes = standing.topic_interval_minutes
            defaults.append("interval_minutes")
        if max_videos_per_run is None:
            max_videos_per_run = standing.topic_max_videos
            defaults.append("max_videos_per_run")
    if not MIN_INTERVAL_MINUTES <= interval_minutes <= MAX_INTERVAL_MINUTES:
        raise WatchlistRefused(
            f"a topic is searched every {MIN_INTERVAL_MINUTES} to {MAX_INTERVAL_MINUTES} minutes (a week)"
        )
    if not 1 <= max_videos_per_run <= MAX_VIDEOS_PER_RUN:
        raise WatchlistRefused(f"a topic offers between 1 and {MAX_VIDEOS_PER_RUN} films per search")

    async with pool.acquire() as conn:
        existing = next(
            (
                topic
                for topic in await store.list_topics(conn)
                if topic.phrase.lower() == text.lower() and topic.language == language
            ),
            None,
        )
        if existing is not None:
            return AddedTopic(existing, created=False, defaults_applied=())
        if await store.count_topics(conn) >= settings.max_topics:
            raise WatchlistRefused(
                f"the watch list holds {settings.max_topics} topics, which is its ceiling — ask the operator "
                "to take one off"
            )
        topic = await store.add_topic(
            conn,
            phrase=text,
            language=language,
            interval_minutes=interval_minutes,
            max_videos_per_run=max_videos_per_run,
            added_by=added_by,
        )
    return AddedTopic(topic, created=True, defaults_applied=tuple(defaults))


@dataclass(frozen=True, slots=True)
class Queued:
    video_id: str
    title: str
    created: bool
    # Whether the film is still on its road, so the caller should have it processed now: a new film, or one that had no
    # words yet or no reading. A film already read, given up on or skipped is left alone.
    process: bool = False


async def analyse_film(
    pool,
    providers,
    settings: Settings,
    reference: str,
    *,
    prompt: int | str | None = None,
) -> Queued:
    """One film named by hand. Costs what asking the source about it costs, counted against the same day as everything
    else; the caller then has it processed at once (`Ingest.start_now`) rather than left to the loop's next pass. Not an
    alert: a film named by hand ends quiet, because whoever asked is already looking."""
    prompt_id = await _prompt_id(pool, prompt)
    try:
        wanted = video_id(reference)
    except SourceError as err:
        raise WatchlistRefused(str(err)) from err

    source = providers.source
    ceiling = budget.Ceiling(source.name, source.unit, settings.daily_source_units)
    async with pool.acquire() as conn:
        existing = await store.get_video(conn, wanted)
        if existing is not None and existing.state == FILTERED_OUT:
            # Somebody looked at what the filter turned away and wants it: it goes back on the road, by the prompt named here
            # or else the one its channel gave it. Released by another caller in between, it is on its road already.
            if await store.release_filtered(conn, wanted, prompt_id=None if prompt is None else prompt_id):
                return Queued(existing.video_id, existing.title, created=False, process=True)
            existing = await store.get_video(conn, wanted)
        if existing is not None:
            return Queued(
                existing.video_id, existing.title, created=False, process=existing.state in _STILL_ON_ITS_ROAD
            )
        left = await budget.remaining(conn, ceiling, day=budget.utc_day(providers.clock.now()))
    if left < 1:
        raise WatchlistRefused(
            f"the {source.name} source's day is spent ({settings.daily_source_units} {source.unit}); "
            "it starts again at midnight UTC"
        )

    try:
        found = await source.video_details([wanted])
    except SourceError as err:
        raise WatchlistRefused(f"the source could not be asked about {wanted}: {err}") from err
    if not found:
        raise WatchlistRefused(f"the source knows no film {wanted}")

    reason = store.unwanted_reason(found[0], (settings.min_video_seconds, settings.max_video_seconds))
    if reason is not None:
        # Named by hand, and still not kept: say why instead of storing a row nobody wants listed.
        raise WatchlistRefused(f"{found[0].title!r} is {reason}, and the archive does not keep such films")

    async with pool.acquire() as conn:
        await store.upsert_films(
            conn, [store.Discovery(found[0], origin="manual", prompt_id=prompt_id)], now=providers.clock.now()
        )
        await store.add_usage(conn, providers.meter.drain(), day=budget.utc_day(providers.clock.now()))
    return Queued(found[0].video_id, found[0].title, created=True, process=True)
