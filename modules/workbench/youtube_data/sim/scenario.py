"""A scenario: which channels exist, which films appear when, what their captions do, and how badly the providers
behave. Times are in minutes from the start of the run, so the same file replays the same afternoon whenever it is
started — and a film may be published before the start (negative), so the run does not begin on an empty archive."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from ..analysis import Reading

DEFAULT_SCENARIO = Path(__file__).resolve().parent / "scenarios" / "default.json"


class SimChannel(BaseModel):
    channel_id: str
    title: str
    handle: str | None = None
    language: str = ""


class SimCaptions(BaseModel):
    """`immediate`: there when asked. `after_minutes`: absent until that long after publication (automatic captions
    arrive hours late). `async`: the provider takes the request and answers by job, ready after `after_minutes` from
    the request. `never`: this film has none."""

    mode: Literal["immediate", "after_minutes", "never", "async"] = "never"
    after_minutes: int = Field(default=0, ge=0)
    text: str = ""
    language: str = "en"
    automatic: bool = True


class SimVideo(BaseModel):
    video_id: str
    channel: str
    title: str
    published_after_start_minutes: int = 0
    duration_seconds: int | None = 600
    # Live until this many minutes after the start; `None` is not live at all.
    live_until_minutes: int | None = None
    captions: SimCaptions = SimCaptions()
    # A prepared reading, the word `unusable` for a model that answers with something the schema refuses, or nothing
    # for the neutral one.
    reading: dict | Literal["unusable"] | None = None


class SimTranscriptBehaviour(BaseModel):
    # The share of requests the provider refuses outright: 0 never, 1 always. Rolled per film and per attempt from the
    # scenario's seed, so the same run refuses the same requests.
    block_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    latency_ms: int = Field(default=0, ge=0)
    native_credits: int = 1
    # Asking about a film with no captions costs this — a provider that charges for a miss is the one to rehearse with.
    miss_credits: int = 1
    daily_credits: int | None = None


class SimSourceBehaviour(BaseModel):
    latency_ms: int = Field(default=0, ge=0)
    list_units: int = 1
    search_units: int = 100
    details_units: int = 1
    daily_units: int | None = None


class SearchEntry(BaseModel):
    phrase_contains: str
    videos: list[str]


class Scenario(BaseModel):
    seed: int = 0
    channels: list[SimChannel]
    videos: list[SimVideo]
    search: list[SearchEntry] = []
    transcripts: SimTranscriptBehaviour = SimTranscriptBehaviour()
    source: SimSourceBehaviour = SimSourceBehaviour()

    @model_validator(mode="after")
    def _references_exist(self) -> Scenario:
        channels = {channel.channel_id for channel in self.channels}
        ids = [video.video_id for video in self.videos]
        if len(ids) != len(set(ids)):
            raise ValueError("two films in the scenario share an id")
        for video in self.videos:
            if video.channel not in channels:
                raise ValueError(f"film {video.video_id} names channel {video.channel}, which is not in the scenario")
            if isinstance(video.reading, dict):
                Reading.model_validate(video.reading)
        for entry in self.search:
            for video_id in entry.videos:
                if video_id not in ids:
                    raise ValueError(f"search {entry.phrase_contains!r} names film {video_id}, which is not in the scenario")
        return self


def load(path: Path | None = None) -> Scenario:
    target = path or DEFAULT_SCENARIO
    try:
        return Scenario.model_validate(json.loads(target.read_text(encoding="utf-8")))
    except OSError as err:
        raise ValueError(f"the simulation scenario {target} cannot be read: {err}") from err
