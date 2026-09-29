"""Transcripts straight from YouTube, through `youtube-transcript-api`: free, and the reason this whole layer is an
interface. From a home address it works. From a datacenter — Azure included — YouTube refuses the address wholesale,
which the library reports as `RequestBlocked` / `IpBlocked`, and that must read as *blocked*, never as *this film has no
captions*: the first is a fact about us, the second about the film, and the loop treats them differently."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    AgeRestricted,
    CouldNotRetrieveTranscript,
    InvalidVideoId,
    IpBlocked,
    NoTranscriptFound,
    PoTokenRequired,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
    VideoUnplayable,
    YouTubeRequestFailed,
)

from .base import Blocked, Meter, NoTranscript, Transcript, TranscriptResult

# The film is what is wrong, not the way in: no captions, or nothing to caption. A retry a day later may still find
# captions (automatic ones appear hours after upload) — the loop decides that, this only says what was seen.
_NOTHING_THERE = (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
    VideoUnplayable,
    AgeRestricted,
    InvalidVideoId,
)

# We are what is wrong, or YouTube is asking for something we cannot give.
_REFUSED = (RequestBlocked, IpBlocked, PoTokenRequired, YouTubeRequestFailed)


class DirectTranscripts:
    name = "direct"

    def __init__(self, meter: Meter, *, api: YouTubeTranscriptApi | None = None) -> None:
        self._meter = meter
        self._api = api or YouTubeTranscriptApi()

    async def fetch(self, video_id: str, languages: Sequence[str]) -> TranscriptResult:
        # The library is synchronous, and a fetch is two requests to a third party.
        try:
            fetched = await asyncio.to_thread(self._api.fetch, video_id, languages=list(languages))
        except _NOTHING_THERE as err:
            self._meter.record(self.name, "requests", 1)
            return NoTranscript(self.name, type(err).__name__)
        except _REFUSED as err:
            self._meter.record(self.name, "requests", 1)
            return Blocked(self.name, type(err).__name__)
        except CouldNotRetrieveTranscript as err:
            # The library's own name for "something else went wrong": not evidence about the film.
            self._meter.record(self.name, "requests", 1)
            return Blocked(self.name, type(err).__name__)
        self._meter.record(self.name, "requests", 1)

        text = " ".join(snippet.text.strip() for snippet in fetched.snippets if snippet.text.strip())
        if not text:
            return NoTranscript(self.name, "the captions are empty")
        return Transcript(
            text=text,
            language=fetched.language_code,
            automatic=fetched.is_generated,
            provider=self.name,
        )

    async def poll(self, job_id: str) -> TranscriptResult:
        return Blocked(self.name, "this provider has no jobs to poll")
