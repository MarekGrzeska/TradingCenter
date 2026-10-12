"""The three things this package asks of the outside world, as protocols, and the answers it can get back. A provider is
a class that fits one of them; which ones run is a setting (`providers/build.py`), so a new transcript provider is a
class and a line in `.env`, not a change to the loop.

The answers are values rather than exceptions wherever the loop has to *decide* something from them: "this film has no
captions" and "this provider will not let us in" are different next steps, and an exception would flatten both into
the same `except`."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

# --- films ----------------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ChannelInfo:
    channel_id: str
    title: str
    handle: str | None = None
    # `UU` + the id's tail is the uploads playlist by convention, so a source that cannot ask still knows it.
    uploads_playlist_id: str | None = None


@dataclass(frozen=True, slots=True)
class VideoRef:
    """What a source knows about a film before anyone has read a word of it. `duration_seconds` is `None` for a premiere
    that has not run yet; `audio_language` is what the uploader declared the film speaks, when they did."""

    video_id: str
    channel_id: str | None
    channel_title: str
    title: str
    published_at: datetime
    duration_seconds: int | None = None
    live_status: str = "none"  # none | live | upcoming
    audio_language: str | None = None
    simulated: bool = False


class SourceError(Exception):
    """A film source could not answer. The loop leaves the archive as it was and tries again on the next pass."""


class SourceUnavailable(SourceError):
    """The source did not answer usefully — a network error, a 5xx, a document that would not parse."""


class QuotaExceeded(SourceError):
    """The source's own daily allowance is spent. Not retried before the day turns."""


class ChannelNotFound(SourceError):
    """The reference names no channel that exists."""


class UnsupportedReference(SourceError):
    """The reference names no channel or film in any form YouTube resolves. Says what to give instead."""


class VideoSource(Protocol):
    name: str
    # What this source is paid in, and what one search costs of it: the loop's daily ceiling is arithmetic over these.
    unit: str

    @property
    def search_cost(self) -> int: ...

    async def resolve_channel(self, reference: str) -> ChannelInfo: ...

    async def latest_videos(self, channel: ChannelInfo) -> list[VideoRef]: ...

    async def search(
        self, phrase: str, *, language: str, published_after: datetime | None, limit: int
    ) -> list[VideoRef]: ...

    async def video_details(self, video_ids: Sequence[str]) -> list[VideoRef]: ...


# --- transcripts ----------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TranscriptRequest:
    """What a transcript provider is told about the film: enough to price it before asking, and to cut a long one."""

    video_id: str
    duration_seconds: int | None
    # Captions are asked for in these, in order — the film's own language alone when it is known (`for_film`).
    languages: tuple[str, ...]
    audio_language: str | None = None

    @classmethod
    def for_film(
        cls, video_id: str, *, duration_seconds: int | None, audio_language: str | None, fallback: Sequence[str]
    ) -> TranscriptRequest:
        # Captions in another language than the film speaks are a translation, and a market reading of a translation
        # loses the names and the numbers.
        languages = (audio_language,) if audio_language else tuple(fallback)
        return cls(video_id, duration_seconds, languages, audio_language)


@dataclass(frozen=True, slots=True)
class Transcript:
    """`text` is paragraphs, each opening with its time from the start of the film (`[MM:SS]`). `model` names the model
    that wrote it down, for a provider that listens rather than reads captions."""

    text: str
    language: str
    automatic: bool
    provider: str
    simulated: bool = False
    model: str | None = None


@dataclass(frozen=True, slots=True)
class NoTranscript:
    """The provider answered, and it has no text for this film. `charged` is whether asking cost anything, which the
    loop records either way: a miss that costs a credit is still a credit."""

    provider: str
    reason: str
    charged: bool = False


@dataclass(frozen=True, slots=True)
class Blocked:
    """The provider did not let us in, or did not answer. Says nothing about the film — the loop must not count it as
    an attempt, or a datacenter address refused wholesale would read as a run of films with no captions."""

    provider: str
    reason: str


TranscriptResult = Transcript | NoTranscript | Blocked


class TranscriptProvider(Protocol):
    name: str
    unit: str
    # A provider that listens to the film is worth asking about one with no captions; one that reads captions is not.
    listens: bool

    def price(self, request: TranscriptRequest) -> int:
        """What asking about this film costs, in `unit`, so the loop asks only when the day can pay for it."""
        ...

    async def fetch(self, request: TranscriptRequest) -> TranscriptResult: ...


def stamp(seconds: float) -> str:
    """`[MM:SS]`, or `[H:MM:SS]` past the hour — the one spelling every transcript in the archive uses."""
    whole = int(seconds)
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    return f"[{hours}:{minutes:02d}:{secs:02d}]" if hours else f"[{minutes:02d}:{secs:02d}]"


# --- readings -------------------------------------------------------------------------------------------------------


class ReadingUnusable(Exception):
    """The model answered with something this package will not store. Kept apart from a refusal: either way the film
    stays unread until the next pass, but only this one is a fact about the model. `tokens` is what the answer cost,
    since a provider bills an answer this package throws away."""

    def __init__(self, message: str, *, tokens: int = 0) -> None:
        super().__init__(message)
        self.tokens = tokens


# --- what was spent -------------------------------------------------------------------------------------------------


class Meter:
    """What each provider was asked for since the loop last looked, in the provider's own unit: API units, requests,
    seconds of film, tokens. Providers write to it as they are called and the loop drains it into `usage`, so a call
    that ends in an exception was still counted."""

    def __init__(self) -> None:
        self._spent: defaultdict[tuple[str, str], int] = defaultdict(int)

    def record(self, provider: str, unit: str, amount: int) -> None:
        if amount:
            self._spent[(provider, unit)] += amount

    def drain(self) -> dict[tuple[str, str], int]:
        spent = dict(self._spent)
        self._spent.clear()
        return spent
