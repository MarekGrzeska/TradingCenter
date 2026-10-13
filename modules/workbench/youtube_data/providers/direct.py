"""Transcripts straight from YouTube, through `youtube-transcript-api`: free, and the reason this whole layer is an
interface. From a home address it works. From a datacenter — Azure included — YouTube refuses the address wholesale,
which the library reports as `RequestBlocked` / `IpBlocked`, and that must read as *blocked*, never as *this film has no
captions*: the first is a fact about us, the second about the film, and the loop treats them differently."""

from __future__ import annotations

import asyncio

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

from .base import (
    Blocked,
    Meter,
    NoTranscript,
    Transcript,
    TranscriptRequest,
    TranscriptResult,
    stamp,
)

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

FETCH_TIMEOUT_SECONDS = 60

# Captions arrive as a line every few seconds; a paragraph every half minute keeps the times without a line per breath.
PARAGRAPH_SECONDS = 30.0


def paragraphs(snippets: list[tuple[float, str]], window: float = PARAGRAPH_SECONDS) -> str:
    """`(start, text)` caption lines as paragraphs, each opening with the time of its first line."""
    out: list[str] = []
    current: list[str] = []
    start: float | None = None
    for at, text in snippets:
        if start is None:
            start = at
        elif at - start >= window and current:
            out.append(f"{stamp(start)} {' '.join(current)}")
            current, start = [], at
        current.append(text)
    if current and start is not None:
        out.append(f"{stamp(start)} {' '.join(current)}")
    return "\n".join(out)


class DirectTranscripts:
    name = "direct"
    unit = "requests"
    listens = False

    def __init__(self, meter: Meter, *, api: YouTubeTranscriptApi | None = None) -> None:
        self._meter = meter
        self._api = api or YouTubeTranscriptApi()

    def price(self, request: TranscriptRequest) -> int:
        return 1

    async def fetch(self, request: TranscriptRequest) -> TranscriptResult:
        # The library is synchronous, and a fetch is two requests to a third party. It sets no timeout of its own, so one
        # half-open connection would hold the whole loop; the thread outlives a timeout, the loop does not wait for it.
        self._meter.record(self.name, self.unit, 1)
        try:
            fetched = await asyncio.wait_for(
                asyncio.to_thread(self._api.fetch, request.video_id, languages=list(request.languages)),
                FETCH_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            return Blocked(self.name, f"no answer within {FETCH_TIMEOUT_SECONDS} s")
        except _NOTHING_THERE as err:
            return NoTranscript(self.name, type(err).__name__)
        except _REFUSED as err:
            return Blocked(self.name, type(err).__name__)
        except CouldNotRetrieveTranscript as err:
            # The library's own name for "something else went wrong": not evidence about the film.
            return Blocked(self.name, type(err).__name__)
        except OSError as err:
            # `requests` wraps only HTTP errors in the library's own type; a refused connection, a timeout or a broken
            # TLS handshake arrive as `requests.RequestException`, which is an `OSError`.
            return Blocked(self.name, type(err).__name__)

        lines = [(snippet.start, " ".join(snippet.text.split())) for snippet in fetched.snippets]
        text = paragraphs([(at, line) for at, line in lines if line])
        if not text:
            return NoTranscript(self.name, "the captions are empty")
        return Transcript(
            text=text,
            language=fetched.language_code,
            automatic=fetched.is_generated,
            provider=self.name,
        )
