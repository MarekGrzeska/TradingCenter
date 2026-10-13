"""The simulated providers — a source, a transcriber and a model — each a protocol from `providers/base.py` and
`analysis.py` over the shared `World`."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from ..analysis import Analysis, Film, Reading
from ..providers.base import (
    Blocked,
    ChannelInfo,
    ChannelNotFound,
    NoTranscript,
    QuotaExceeded,
    ReadingUnusable,
    Transcript,
    TranscriptRequest,
    TranscriptResult,
    VideoRef,
    stamp,
)
from ..providers.refs import channel_ref, uploads_playlist
from .world import World

UNIT = "sim_units"
VIDEO_SECONDS = "sim_video_seconds"

# What the reading of a film without a prepared one says. Neutral on purpose: a simulation that invents opinions would
# be read as if it had them.
NEUTRAL = Reading(
    summary_pl="Symulowany odczyt bez przygotowanej treści: film nie zawiera tez rynkowych.",
    key_points=[],
    instruments=[],
    predictions=[],
    topics=[],
    impact_score=1,
)


class SimSource:
    name = "sim"
    unit = UNIT

    def __init__(self, world: World) -> None:
        self._world = world

    @property
    def search_cost(self) -> int:
        source = self._world.scenario.source
        return source.search_units + source.details_units

    async def _pay(self, units: int) -> None:
        behaviour = self._world.scenario.source
        await self._world.lag(behaviour.latency_ms)
        if not self._world.spend(self.name, UNIT, units, cap=behaviour.daily_units):
            raise QuotaExceeded("the simulated source's daily allowance is spent")

    async def resolve_channel(self, reference: str) -> ChannelInfo:
        await self._pay(self._world.scenario.source.list_units)
        ref = channel_ref(reference)
        channel = (
            self._world.channel(ref.value) if ref.kind == "id" else self._world.channel_by_handle(ref.value)
        )
        if channel is None:
            raise ChannelNotFound(f"the simulation has no channel {reference!r}")
        return ChannelInfo(
            channel_id=channel.channel_id,
            title=channel.title,
            handle=channel.handle,
            uploads_playlist_id=uploads_playlist(channel.channel_id),
        )

    async def latest_videos(self, channel: ChannelInfo) -> list[VideoRef]:
        source = self._world.scenario.source
        await self._pay(source.list_units + source.details_units)
        films = [
            video
            for video in self._world.scenario.videos
            if video.channel == channel.channel_id and self._world.visible(video)
        ]
        films.sort(key=self._world.published_at, reverse=True)
        return [self._world.ref(video) for video in films[:15]]

    async def search(
        self, phrase: str, *, language: str, published_after: datetime | None, limit: int
    ) -> list[VideoRef]:
        source = self._world.scenario.source
        await self._pay(source.search_units + source.details_units)
        wanted = phrase.lower()
        ids: list[str] = []
        for entry in self._world.scenario.search:
            if entry.phrase_contains.lower() in wanted:
                ids.extend(video_id for video_id in entry.videos if video_id not in ids)
        films = [
            video
            for video_id in ids
            if (video := self._world.video(video_id)) is not None
            and self._world.visible(video)
            and (published_after is None or self._world.published_at(video) >= published_after)
        ]
        films.sort(key=self._world.published_at, reverse=True)
        return [self._world.ref(video) for video in films[: max(limit, 0)]]

    async def video_details(self, video_ids: Sequence[str]) -> list[VideoRef]:
        await self._pay(self._world.scenario.source.details_units)
        found = (self._world.video(video_id) for video_id in video_ids)
        return [self._world.ref(video) for video in found if video is not None and self._world.visible(video)]


class SimTranscriber:
    """Gemini's stand-in: hears what the scenario says the film says, paid in seconds of film."""

    name = "sim"
    unit = VIDEO_SECONDS
    model = "sim"

    def __init__(self, world: World) -> None:
        self._world = world

    def price(self, request: TranscriptRequest) -> int:
        return request.duration_seconds or 0

    async def fetch(self, request: TranscriptRequest) -> TranscriptResult:
        behaviour = self._world.scenario.transcriber
        await self._world.lag(behaviour.latency_ms)
        if self._world.roll(request.video_id) < behaviour.block_ratio:
            return Blocked(self.name, "the simulated model is crowded")

        video = self._world.video(request.video_id)
        if video is None or not self._world.visible(video):
            return NoTranscript(self.name, "the simulation has no such film")
        if not request.duration_seconds:
            return NoTranscript(self.name, "the film's length is not known yet")
        if not self._world.spend(self.name, VIDEO_SECONDS, request.duration_seconds, cap=behaviour.daily_video_seconds):
            return Blocked(self.name, "the simulated model's daily seconds of film are spent")
        if not video.speech.strip():
            # Music over a chart: a real model answers with nothing, and that is no transcript, not an empty one.
            return NoTranscript(self.name, "there is nothing to write down", charged=True)
        return Transcript(
            text=f"{stamp(0)} {video.speech.strip()}",
            language=request.audio_language or video.language,
            automatic=True,
            provider=self.name,
            simulated=True,
            model=self.model,
        )


class SimAnalyser:
    model = "sim"

    def __init__(self, world: World) -> None:
        self._world = world

    async def read(self, film: Film, transcript: str, *, profile: str) -> Analysis:
        video = self._world.video(film.video_id)
        prepared = None if video is None else video.reading
        if prepared == "unusable":
            raise ReadingUnusable(
                "the simulated model answered with something that breaks the schema", tokens=len(transcript) // 4
            )
        reading = NEUTRAL if prepared is None else Reading.model_validate(prepared)
        return Analysis(
            reading=reading,
            model=self.model,
            # A quarter of a token per character is the rule of thumb, and enough to make the daily limit bite.
            input_tokens=len(transcript) // 4,
            output_tokens=len(reading.summary_pl) // 4 + 40,
            simulated=True,
        )
