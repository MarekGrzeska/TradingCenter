"""What this package answers with — the published shape, and the one place the terminal learns what a film is.

Every reading field is present on every film and empty where there is no reading, and every film says whether it came from
the simulation. A field that vanishes when a model has not run is a field a consumer cannot tell from a contract that moved,
and a film that does not say it is simulated is one nobody can tell from a real one."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from .models import Channel, Topic
from .store import Film

SCORE = "what a model made of this film's market impact, 1..10 — 1 is commentary with nothing new, 10 a global event"
WATCH = "https://www.youtube.com/watch?v="


class Problem(BaseModel):
    """One refusal shape for every route, so a consumer handles one thing."""

    detail: str
    cause: Literal["module", "source", "request"] = "module"
    retryable: bool = False


class InstrumentOut(BaseModel):
    name: str
    epic: str | None = Field(default=None, description="a ticker or epic, only where the speaker gave or implied one")
    sentiment: Literal["bullish", "bearish", "neutral"]
    conviction: int = Field(description="how sure the speaker sounds, 1..5 — not how sure the model is")
    horizon: Literal["intraday", "swing", "long"]


class PredictionOut(BaseModel):
    instrument: str
    claim: str
    level: float | None = None
    by: date | None = None


class ReadingOut(BaseModel):
    """A model's reading of one film — a fact about what a model said, never published without naming it."""

    profile: str
    summary_pl: str
    key_points: list[str]
    instruments: list[InstrumentOut]
    predictions: list[PredictionOut]
    topics: list[str]
    impact_score: int = Field(description=SCORE)
    model: str
    analysed_at: datetime
    simulated: bool = Field(description="produced by the simulation, about a film that does not exist")


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
    reading: ReadingOut | None = Field(default=None, description="null until a model has read it")

    @classmethod
    def of(cls, film: Film) -> VideoOut:
        video = film.video
        reading = None
        if film.reading is not None and film.reading_model and film.analysed_at:
            reading = ReadingOut(
                profile=video.profile,
                model=film.reading_model,
                analysed_at=film.analysed_at,
                simulated=bool(film.reading_simulated),
                **film.reading,
            )
        return cls(
            video_id=video.video_id,
            url=WATCH + video.video_id,
            title=video.title,
            channel_id=video.channel_id,
            channel_title=video.channel_title,
            published_at=video.published_at,
            duration_seconds=video.duration_seconds,
            live_status=video.live_status,  # type: ignore[arg-type]
            state=video.state,  # type: ignore[arg-type]
            skip_reason=video.skip_reason,
            origins=list(video.origins),
            attempts=video.attempts,
            next_attempt_at=video.next_attempt_at,
            notified_at=video.notified_at,
            discovered_at=video.discovered_at,
            simulated=video.simulated,
            reading=reading,
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


AlertRule = Literal["always", "threshold", "never"]


class ChannelOut(BaseModel):
    channel_id: str
    title: str
    handle: str | None = None
    language: str
    profile: str
    alert_rule: AlertRule
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
            profile=channel.profile,
            alert_rule=channel.alert_rule,  # type: ignore[arg-type]
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
    alert_rule: AlertRule = "threshold"
    profile: str = "market"
    language: str = ""


class ChannelPatch(BaseModel):
    alert_rule: AlertRule | None = None
    profile: str | None = None
    active: bool | None = Field(default=None, description="false pauses discovery without taking anything off")


class ChannelAddedOut(BaseModel):
    channel: ChannelOut
    created: bool = Field(description="false where the channel was already on the list, which is left as it was")


class TopicOut(BaseModel):
    id: int
    phrase: str
    language: str
    interval_minutes: int
    max_videos_per_run: int
    profile: str
    alert_rule: AlertRule
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
            profile=topic.profile,
            alert_rule=topic.alert_rule,  # type: ignore[arg-type]
            active=topic.active,
            added_by=topic.added_by,  # type: ignore[arg-type]
            added_at=topic.added_at,
            last_run_at=topic.last_run_at,
        )


class TopicsOut(BaseModel):
    topics: list[TopicOut]
    ceiling: int


class TopicIn(BaseModel):
    phrase: str
    language: str = ""
    interval_minutes: int | None = Field(default=None, description="null takes the setting's default")
    max_videos_per_run: int | None = Field(default=None, description="null takes the setting's default")
    alert_rule: AlertRule = "threshold"
    profile: str = "market"


class TopicPatch(BaseModel):
    alert_rule: AlertRule | None = None
    active: bool | None = None


class TopicAddedOut(BaseModel):
    topic: TopicOut
    created: bool
    defaults_applied: list[str] = Field(description="which limits came from the settings rather than from the request")


class AnalyseIn(BaseModel):
    reference: str = Field(description="a YouTube film address or id")


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
    model_configured: bool = Field(description="false means no reading is being made, by configuration")
    alerts_configured: bool = Field(description="false means nobody is told, by configuration")
    channels_active: int
    topics_active: int
    providers: list[ProviderOut]
    waiting: dict[str, int] = Field(description="films still on their road, by state — exact")
    recent: dict[str, int] = Field(description="films published in the last `recent_days`, by state")
    recent_days: int
    loop: LoopOut | None = None
    stale: bool = Field(description="the loop has not completed a pass for several intervals")
