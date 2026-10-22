"""The shapes tools answer with, lean on purpose. The REST contract's models carry a sentence of description per field for the
terminal's types; a model reads every description of every tool in every turn, so the tools answer in smaller ones."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from ..contract import (
    ChannelOut,
    ProviderOut,
    StateOut,
    TopicOut,
    VideoDetailOut,
)

# The most of a reading's text one tool call returns: the text is up to twenty kilobytes, and a model reads all of it.
MAX_READING_CHARS = 8_000


class ChannelBrief(BaseModel):
    channel_id: str
    title: str
    handle: str | None
    active: bool
    added_by: str
    last_discovery_at: datetime | None

    @classmethod
    def of(cls, channel: ChannelOut) -> ChannelBrief:
        return cls(**{name: getattr(channel, name) for name in cls.model_fields})


class TopicBrief(BaseModel):
    id: int
    phrase: str
    interval_minutes: int
    max_videos_per_run: int
    active: bool
    added_by: str
    last_run_at: datetime | None

    @classmethod
    def of(cls, topic: TopicOut) -> TopicBrief:
        return cls(**{name: getattr(topic, name) for name in cls.model_fields})


class ProviderBrief(BaseModel):
    role: str
    name: str
    unit: str
    spent_today: int
    ceiling: int
    exhausted: bool
    blocked: bool

    @classmethod
    def of(cls, provider: ProviderOut) -> ProviderBrief:
        return cls(**{name: getattr(provider, name) for name in cls.model_fields})


class PromptBrief(BaseModel):
    name: str = Field(description="what follow_channel and analyse_video take as `prompt`")
    seeded: bool = Field(description="the one that is always there, and the one a call without `prompt` takes")


class StatusBrief(BaseModel):
    simulating: bool
    model_configured: bool
    alerts_configured: bool
    stale: bool
    loop_age_seconds: float | None
    providers: list[ProviderBrief]
    waiting: dict[str, int]
    recent: dict[str, int]
    channels: list[ChannelBrief]
    topics: list[TopicBrief]
    prompts: list[PromptBrief]

    @classmethod
    def of(
        cls, state: StateOut, channels: list[ChannelOut], topics: list[TopicOut], prompts: list[PromptBrief]
    ) -> StatusBrief:
        return cls(
            simulating=state.simulating,
            model_configured=state.model_configured,
            alerts_configured=state.alerts_configured,
            stale=state.stale,
            loop_age_seconds=None if state.loop is None else state.loop.age_seconds,
            providers=[ProviderBrief.of(provider) for provider in state.providers],
            waiting=state.waiting,
            recent=state.recent,
            channels=[ChannelBrief.of(channel) for channel in channels],
            topics=[TopicBrief.of(topic) for topic in topics],
            prompts=prompts,
        )


class ReadingBrief(BaseModel):
    prompt: str = Field(description="the name of the prompt that made this reading")
    prompt_version: int
    summary_pl: str
    text: str = Field(description="the reading, in Markdown, laid out as its prompt asked")
    text_cut: bool = Field(description="true means the text was longer than a tool call carries")
    impact_score: int
    model: str
    analysed_at: datetime


class VideoDetail(BaseModel):
    video_id: str
    url: str
    title: str
    channel_title: str
    published_at: datetime
    duration_seconds: int | None
    state: str
    simulated: bool
    readings: list[ReadingBrief] = Field(description="the film's own prompt's first; empty means no model has read it")

    @classmethod
    def of(cls, video: VideoDetailOut) -> VideoDetail:
        return cls(
            video_id=video.video_id,
            url=video.url,
            title=video.title,
            channel_title=video.channel_title,
            published_at=video.published_at,
            duration_seconds=video.duration_seconds,
            state=video.state,
            simulated=video.simulated,
            readings=[
                ReadingBrief(
                    prompt=reading.prompt_name,
                    prompt_version=reading.prompt_version,
                    summary_pl=reading.summary_pl,
                    text=reading.text[:MAX_READING_CHARS],
                    text_cut=len(reading.text) > MAX_READING_CHARS,
                    impact_score=reading.impact_score,
                    model=reading.model,
                    analysed_at=reading.analysed_at,
                )
                for reading in video.readings
            ],
        )
