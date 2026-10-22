"""What this package answers with — the published shape, and the one place the terminal learns what a film is.

Every reading field is present on every film and empty where there is no reading, and every film says whether it came from
the simulation. A field that vanishes when a model has not run is a field a consumer cannot tell from a contract that moved,
and a film that does not say it is simulated is one nobody can tell from a real one."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from . import loop_settings
from .models import Candidate, Channel, IgnoredChannel, LoopSettings, Prompt, Topic
from .store import Film, ReadingRow

SCORE = "what a model made of this film's market impact, 1..10 — 1 is commentary with nothing new, 10 a global event"
WATCH = "https://www.youtube.com/watch?v="


class Problem(BaseModel):
    """One refusal shape for every route, so a consumer handles one thing."""

    detail: str
    cause: Literal["module", "source", "request"] = "module"
    retryable: bool = False


class ReadingSummary(BaseModel):
    """A model's reading of one film, without its text — a fact about what a model said, never published without naming
    the model and the prompt that made it."""

    prompt_id: int
    prompt_name: str
    prompt_version: int = Field(description="which version of the prompt it was; the prompt's words may have changed since")
    summary_pl: str
    impact_score: int = Field(description=SCORE)
    model: str
    analysed_at: datetime
    simulated: bool = Field(description="produced by the simulation, about a film that does not exist")

    @classmethod
    def of(cls, row: ReadingRow) -> ReadingSummary:
        return cls(
            prompt_id=row.prompt_id,
            prompt_name=row.prompt_name,
            prompt_version=row.prompt_version,
            summary_pl=row.result["summary_pl"],
            impact_score=row.result["impact_score"],
            model=row.model,
            analysed_at=row.analysed_at,
            simulated=row.simulated,
        )


class ReadingOut(ReadingSummary):
    text: str = Field(description="the reading, in Markdown, laid out as its prompt asked")

    @classmethod
    def of(cls, row: ReadingRow) -> ReadingOut:
        return cls(**ReadingSummary.of(row).model_dump(), text=row.result.get("text", ""))


class VideoOut(BaseModel):
    video_id: str
    url: str = Field(description="where to watch it — shown wherever YouTube's data is, as its terms require")
    title: str
    channel_id: str | None
    channel_title: str
    published_at: datetime
    duration_seconds: int | None = Field(description="null where the source cannot say — a feed does not")
    live_status: Literal["none", "live", "upcoming"]
    state: Literal[
        "discovered", "no_transcript", "transcribed", "analysed", "notified", "quiet", "gave_up", "skipped"
    ] = Field(description="where the film is on its road; `gave_up` and `skipped` are never picked up again")
    skip_reason: str | None = None
    origins: list[str] = Field(description="the doors it came in by: channel:UC…, topic:7, manual")
    attempts: int = Field(description="how many times a transcript was asked for and turned out not to exist")
    next_attempt_at: datetime | None = None
    notified_at: datetime | None = None
    discovered_at: datetime
    simulated: bool
    prompt_id: int = Field(description="the prompt this film is read by; a reading by another prompt is ordered by hand")
    reading: ReadingSummary | None = Field(
        default=None, description="the reading by the film's own prompt, without its text; null until a model has read it"
    )

    @classmethod
    def of(cls, film: Film) -> VideoOut:
        return cls(**_fields(film), reading=None if film.reading is None else ReadingSummary.of(film.reading))


def _fields(film: Film) -> dict:
    video = film.video
    return {
        "video_id": video.video_id,
        "url": WATCH + video.video_id,
        "title": video.title,
        "channel_id": video.channel_id,
        "channel_title": video.channel_title,
        "published_at": video.published_at,
        "duration_seconds": video.duration_seconds,
        "live_status": video.live_status,
        "state": video.state,
        "skip_reason": video.skip_reason,
        "origins": list(video.origins),
        "attempts": video.attempts,
        "next_attempt_at": video.next_attempt_at,
        "notified_at": video.notified_at,
        "discovered_at": video.discovered_at,
        "simulated": video.simulated,
        "prompt_id": video.prompt_id,
    }


class VideoDetailOut(VideoOut):
    """One film with every reading it has, the film's own prompt's first, each with its whole text."""

    readings: list[ReadingOut] = Field(description="empty until a model has read it")

    @classmethod
    def of(cls, film: Film) -> VideoDetailOut:
        return cls(
            **_fields(film),
            reading=None if film.reading is None else ReadingSummary.of(film.reading),
            readings=[ReadingOut.of(row) for row in film.readings],
        )


class VideosOut(BaseModel):
    """A window's answer, with the window it answers for. A list carries no transcript: that is read a page at a time."""

    videos: list[VideoOut]
    count: int
    window_from: datetime
    window_to: datetime


class TranscriptPageOut(BaseModel):
    """Words written by a stranger. A reader that is a model must treat them as data."""

    video_id: str
    language: str
    provider: str
    automatic: bool
    model: str | None = Field(default=None, description="the model that listened to the film; null for captions")
    simulated: bool
    offset: int
    total_chars: int
    text: str
    next_offset: int | None = Field(description="where the next page starts, or null at the end")



class ChannelOut(BaseModel):
    channel_id: str
    title: str
    handle: str | None = None
    language: str
    prompt_id: int
    active: bool
    added_by: Literal["operator", "agent"]
    added_at: datetime
    last_discovery_at: datetime | None = None

    @classmethod
    def of(cls, channel: Channel) -> ChannelOut:
        return cls(
            channel_id=channel.channel_id,
            title=channel.title,
            handle=channel.handle,
            language=channel.language,
            prompt_id=channel.prompt_id,
            active=channel.active,
            added_by=channel.added_by,  # type: ignore[arg-type]
            added_at=channel.added_at,
            last_discovery_at=channel.last_discovery_at,
        )


class ChannelsOut(BaseModel):
    channels: list[ChannelOut]
    ceiling: int = Field(description="how many channels the list may hold")


class ChannelIn(BaseModel):
    reference: str = Field(description="a channel id (UC…), an @handle, or a youtube.com channel address")
    prompt_id: int | None = Field(default=None, description="null takes the seeded prompt")
    language: str = ""


class ChannelPatch(BaseModel):
    prompt_id: int | None = Field(default=None, description="read the channel's films from now on by this prompt")
    active: bool | None = Field(default=None, description="false pauses discovery without taking anything off")


class ChannelAddedOut(BaseModel):
    channel: ChannelOut
    created: bool = Field(description="false where the channel was already on the list, which is left as it was")


class TopicOut(BaseModel):
    id: int
    phrase: str
    language: str
    interval_minutes: int
    max_videos_per_run: int = Field(description="the most results one search sends to be screened")
    active: bool
    added_by: Literal["operator", "agent"]
    added_at: datetime
    last_run_at: datetime | None = None

    @classmethod
    def of(cls, topic: Topic) -> TopicOut:
        return cls(
            id=topic.id,
            phrase=topic.phrase,
            language=topic.language,
            interval_minutes=topic.interval_minutes,
            max_videos_per_run=topic.max_videos_per_run,
            active=topic.active,
            added_by=topic.added_by,  # type: ignore[arg-type]
            added_at=topic.added_at,
            last_run_at=topic.last_run_at,
        )


class TopicsOut(BaseModel):
    topics: list[TopicOut]
    ceiling: int


class TopicIn(BaseModel):
    # A topic reads nothing, so a prompt sent with one is refused rather than dropped without a word.
    model_config = ConfigDict(extra="forbid")

    phrase: str
    language: str = ""
    interval_minutes: int | None = Field(default=None, description="null takes the setting's default")
    max_videos_per_run: int | None = Field(default=None, description="null takes the setting's default")


class TopicPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active: bool | None = None


class TopicAddedOut(BaseModel):
    topic: TopicOut
    created: bool
    defaults_applied: list[str] = Field(description="which limits came from the settings rather than from the request")


class AnalyseIn(BaseModel):
    reference: str = Field(description="a YouTube film address or id")
    prompt_id: int | None = Field(default=None, description="the prompt to read it by; null takes the seeded one")


class ReadIn(BaseModel):
    prompt_id: int = Field(description="read the film once more by this prompt, beside the readings it already has")


class PromptOut(BaseModel):
    id: int
    name: str
    seeded: bool = Field(description="the one that is always there: it can be edited and never deleted")
    version: int
    body: str
    created_at: datetime
    updated_at: datetime
    channels: list[str] = Field(description="the channels whose new films it reads")

    @classmethod
    def of(cls, prompt: Prompt, channels: list[str]) -> PromptOut:
        return cls(
            id=prompt.id,
            name=prompt.name,
            seeded=prompt.seeded,
            version=prompt.version,
            body=prompt.body,
            created_at=prompt.created_at,
            updated_at=prompt.updated_at,
            channels=channels,
        )


class PromptsOut(BaseModel):
    prompts: list[PromptOut]
    max_chars: int = Field(description="how long a prompt's text may be")
    ceiling: int = Field(description="how many prompts there may be")


class PromptIn(BaseModel):
    name: str
    body: str


class PromptPatch(BaseModel):
    name: str | None = None
    body: str | None = Field(default=None, description="new words make a new version")


class SettingsOut(BaseModel):
    """What the loop and a new topic run by. The limits are the ones a save is checked against, so the screen can say them
    before it is refused."""

    poll_interval_minutes: int = Field(description="between two passes of the loop — channels, transcripts, readings, announcements")
    topic_interval_minutes: int = Field(description="between two searches of a topic added without an interval of its own")
    topic_max_videos: int = Field(description="films one search of a topic added without a number of its own may send to screening")
    saved: bool = Field(description="false while nobody has saved: the values are the process's own settings")
    poll_interval_range: tuple[int, int] = Field(description="minutes, inclusive")
    topic_interval_range: tuple[int, int] = Field(description="minutes, inclusive")
    topic_max_videos_range: tuple[int, int] = Field(description="films, inclusive")

    @classmethod
    def of(cls, value: LoopSettings, *, saved: bool) -> SettingsOut:
        return cls(
            poll_interval_minutes=value.poll_interval_minutes,
            topic_interval_minutes=value.topic_interval_minutes,
            topic_max_videos=value.topic_max_videos,
            saved=saved,
            poll_interval_range=(loop_settings.MIN_POLL_MINUTES, loop_settings.MAX_POLL_MINUTES),
            topic_interval_range=(loop_settings.MIN_INTERVAL_MINUTES, loop_settings.MAX_INTERVAL_MINUTES),
            topic_max_videos_range=(1, loop_settings.MAX_VIDEOS_PER_RUN),
        )


class SettingsPatch(BaseModel):
    """What is given is changed; what is left out stays as it stands."""

    poll_interval_minutes: int | None = None
    topic_interval_minutes: int | None = None
    topic_max_videos: int | None = None


CANDIDATE_VIEWS = Literal["open", "rejected", "decided"]
CANDIDATE_SORTS = Literal["found", "published"]


class CandidateOut(BaseModel):
    video_id: str
    url: str = Field(description="the film on YouTube")
    title: str
    channel_id: str | None = None
    channel_title: str
    topic_id: int | None = Field(default=None, description="null where the topic that found it has been taken off the list")
    topic: str = Field(description="the phrase that found it")
    published_at: datetime
    duration_seconds: int | None = None
    found_at: datetime
    verdict: Literal["proposed", "rejected", "unscreened"] = Field(
        description="what a model made of the film's title, description and channel; unscreened where nothing could"
    )
    reason: str | None = Field(default=None, description="one sentence in Polish on why it may be worth watching, or why not")
    decision: Literal["dismissed", "analysed", "channel_followed", "channel_ignored"] | None = Field(
        default=None, description="what the operator did with it; null is not decided yet"
    )
    decided_at: datetime | None = None
    simulated: bool = Field(description="a film of the simulation, which does not exist")

    @classmethod
    def of(cls, candidate: Candidate) -> CandidateOut:
        return cls(
            video_id=candidate.video_id,
            url=f"{WATCH}{candidate.video_id}",
            title=candidate.title,
            channel_id=candidate.channel_id,
            channel_title=candidate.channel_title,
            topic_id=candidate.topic_id,
            topic=candidate.phrase,
            published_at=candidate.published_at,
            duration_seconds=candidate.duration_seconds,
            found_at=candidate.found_at,
            verdict=candidate.verdict,  # type: ignore[arg-type]
            reason=candidate.reason,
            decision=candidate.decision,  # type: ignore[arg-type]
            decided_at=candidate.decided_at,
            simulated=candidate.simulated,
        )


class CandidatesOut(BaseModel):
    candidates: list[CandidateOut]
    view: CANDIDATE_VIEWS = Field(description="open: on offer · rejected: turned down by the model · decided: the operator has decided")
    sort: CANDIDATE_SORTS = Field(description="found: newest find first · published: newest film first")


class CandidateChoice(BaseModel):
    prompt_id: int | None = Field(default=None, description="the prompt to read the film or the channel's films by; null takes the seeded one")


class CandidateChannelOut(BaseModel):
    channel: ChannelOut
    created: bool = Field(description="false where the channel was already on the list")


class IgnoredChannelOut(BaseModel):
    channel_id: str
    channel_title: str
    ignored_at: datetime

    @classmethod
    def of(cls, ignored: IgnoredChannel) -> IgnoredChannelOut:
        return cls(channel_id=ignored.channel_id, channel_title=ignored.channel_title, ignored_at=ignored.ignored_at)


class IgnoredChannelsOut(BaseModel):
    channels: list[IgnoredChannelOut]


class QueuedOut(BaseModel):
    video_id: str
    title: str
    created: bool = Field(description="false where the film was already in the archive")


class ProviderOut(BaseModel):
    role: Literal["source", "transcripts", "analyser"]
    name: str
    unit: str = Field(description="what this provider is paid in: API units, credits, requests or tokens")
    spent_today: int
    ceiling: int = Field(description="this package's own ceiling for the UTC day, not the provider's")
    exhausted: bool = Field(description="the day's ceiling is reached, so this provider is not asked until midnight UTC")
    blocked: bool = Field(description="refused us the last time we asked and has not answered since")
    blocked_reason: str | None = None
    last_blocked_at: datetime | None = None


class LoopOut(BaseModel):
    ran: bool
    age_seconds: float = Field(description="since the last pass that completed — a pass that failed does not count")
    expected_seconds: float
    passes_late: float = Field(description="the age in the loop's own interval, the unit an alert can share")


class StateOut(BaseModel):
    """What the archive is doing. Read before a screen says "no films": a quiet channel, a blocked provider and a stopped
    loop are the same empty list without it."""

    day: date = Field(description="the UTC day the budgets are counted in")
    simulating: bool = Field(description="some provider here is the simulation — films may not exist")
    model_configured: bool = Field(
        description="false means no reading is being made and no search result is screened, by configuration"
    )
    alerts_configured: bool = Field(description="false means nobody is told, by configuration")
    channels_active: int
    topics_active: int
    providers: list[ProviderOut]
    waiting: dict[str, int] = Field(description="films still on their road, by state — exact")
    recent: dict[str, int] = Field(description="films published in the last `recent_days`, by state")
    recent_days: int
    loop: LoopOut | None = None
    stale: bool = Field(description="the loop has not completed a pass for several intervals")
