"""The shapes tools answer with, lean on purpose. The REST contract's models carry a sentence of description per field for the
terminal's types; a model reads every description of every tool in every turn, so the tools answer in smaller ones."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from ..contract import (
    ChannelOut,
    InstrumentOut,
    PredictionOut,
    ProviderOut,
    StateOut,
    TopicOut,
    VideoOut,
)


class ChannelBrief(BaseModel):
    channel_id: str
    title: str
    handle: str | None
    alert_rule: str
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
    alert_rule: str
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


class StatusBrief(BaseModel):
    simulating: bool
    model_configured: bool
    alerts_configured: bool
    search_supported: bool
    stale: bool
    loop_age_seconds: float | None
    providers: list[ProviderBrief]
    waiting: dict[str, int]
    recent: dict[str, int]
    channels: list[ChannelBrief]
    topics: list[TopicBrief]

    @classmethod
    def of(cls, state: StateOut, channels: list[ChannelOut], topics: list[TopicOut]) -> StatusBrief:
        return cls(
            simulating=state.simulating,
            model_configured=state.model_configured,
            alerts_configured=state.alerts_configured,
            search_supported=state.search_supported,
            stale=state.stale,
            loop_age_seconds=None if state.loop is None else state.loop.age_seconds,
            providers=[ProviderBrief.of(provider) for provider in state.providers],
            waiting=state.waiting,
            recent=state.recent,
            channels=[ChannelBrief.of(channel) for channel in channels],
            topics=[TopicBrief.of(topic) for topic in topics],
        )


class ReadingBrief(BaseModel):
    summary_pl: str
    key_points: list[str]
    instruments: list[InstrumentOut]
    predictions: list[PredictionOut]
    topics: list[str]
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
    reading: ReadingBrief | None

    @classmethod
    def of(cls, video: VideoOut) -> VideoDetail:
        reading = video.reading
        return cls(
            video_id=video.video_id,
            url=video.url,
            title=video.title,
            channel_title=video.channel_title,
            published_at=video.published_at,
            duration_seconds=video.duration_seconds,
            state=video.state,
            simulated=video.simulated,
            reading=None
            if reading is None
            else ReadingBrief(
                summary_pl=reading.summary_pl,
                key_points=reading.key_points,
                instruments=reading.instruments,
                predictions=reading.predictions,
                topics=reading.topics,
                impact_score=reading.impact_score,
                model=reading.model,
                analysed_at=reading.analysed_at,
            ),
        )
