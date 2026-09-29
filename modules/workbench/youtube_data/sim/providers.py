"""The three simulated providers, each a protocol from `providers/base.py` and `analysis.py` over the shared `World`."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from ..analysis import Analysis, Film, Reading
from ..providers.base import (
    Blocked,
    ChannelInfo,
    ChannelNotFound,
    NoTranscript,
    Pending,
    QuotaExceeded,
    ReadingUnusable,
    Transcript,
    TranscriptResult,
    VideoRef,
)
from ..providers.refs import channel_ref, uploads_playlist
from .world import World

UNIT = "sim_units"
CREDIT = "sim_credits"

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
    supports_search = True
    supports_handles = True

    def __init__(self, world: World) -> None:
        self._world = world

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


class SimTranscripts:
    name = "sim"

    def __init__(self, world: World) -> None:
        self._world = world

    def _pay(self, credits: int) -> bool:
        return self._world.spend(self.name, CREDIT, credits, cap=self._world.scenario.transcripts.daily_credits)

    def _transcript(self, text: str, language: str, automatic: bool) -> TranscriptResult:
        if not text.strip():
            # A film whose captions are all silence: real providers call it no transcript, not an empty one.
            return NoTranscript(self.name, "the captions are empty", charged=True)
        return Transcript(text=text, language=language, automatic=automatic, provider=self.name, simulated=True)

    async def fetch(self, video_id: str, languages: Sequence[str]) -> TranscriptResult:
        behaviour = self._world.scenario.transcripts
        await self._world.lag(behaviour.latency_ms)

        # Refused before anything is looked up: a blocked provider does not know whether the film has captions, and
        # neither is any credit spent on the refusal.
        if self._world.roll(video_id) < behaviour.block_ratio:
            return Blocked(self.name, "the simulated provider refused this request")

        video = self._world.video(video_id)
        if video is None or not self._world.visible(video):
            self._pay(behaviour.miss_credits)
            return NoTranscript(self.name, "the simulation has no such film", charged=True)

        captions = video.captions
        if captions.mode == "never":
            self._pay(behaviour.miss_credits)
            return NoTranscript(self.name, "this film has no captions", charged=True)
        if captions.mode == "after_minutes":
            ready = self._world.published_at(video) + timedelta(minutes=captions.after_minutes)
            if self._world.clock.now() < ready:
                self._pay(behaviour.miss_credits)
                return NoTranscript(self.name, "the captions are not there yet", charged=True)
        if captions.mode == "async":
            job_id = f"job-{video_id}-{len(self._world.jobs) + 1}"
            ready = self._world.clock.now() + timedelta(minutes=captions.after_minutes)
            self._world.jobs[job_id] = (video_id, ready)
            return Pending(self.name, job_id)

        if not self._pay(behaviour.native_credits):
            return Blocked(self.name, "the simulated provider's daily credits are spent")
        return self._transcript(captions.text, captions.language, captions.automatic)

    async def poll(self, job_id: str) -> TranscriptResult:
        # Free, as at the real provider: looking at a job is not asking for a transcript.
        job = self._world.jobs.get(job_id)
        if job is None:
            return NoTranscript(self.name, "the simulation has no such job")
        video_id, ready = job
        if self._world.clock.now() < ready:
            return Pending(self.name, job_id)
        video = self._world.video(video_id)
        assert video is not None
        del self._world.jobs[job_id]
        self._pay(self._world.scenario.transcripts.native_credits)
        return self._transcript(video.captions.text, video.captions.language, video.captions.automatic)


class SimAnalyser:
    model = "sim"

    def __init__(self, world: World) -> None:
        self._world = world

    async def read(self, film: Film, transcript: str, *, profile: str) -> Analysis:
        video = self._world.video(film.video_id)
        prepared = None if video is None else video.reading
        if prepared == "unusable":
            raise ReadingUnusable("the simulated model answered with something that breaks the schema")
        reading = NEUTRAL if prepared is None else Reading.model_validate(prepared)
        return Analysis(
            reading=reading,
            model=self.model,
            # A quarter of a token per character is the rule of thumb, and enough to make the daily limit bite.
            input_tokens=len(transcript) // 4,
            output_tokens=len(reading.summary_pl) // 4 + 40,
            simulated=True,
        )
