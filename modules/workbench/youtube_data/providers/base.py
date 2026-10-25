"""The three things this package asks of the outside world, as protocols, and the answers it can get back: films (the
YouTube Data API), their words (Gemini, which listens to the film) and a reading (a model). Which implementation runs is a
setting (`providers/build.py`) — the real one or the simulation.

The answers are values rather than exceptions wherever the loop has to *decide* something from them: "nothing could be
written down for this film" and "the provider will not let us in" are different next steps, and an exception would
flatten both into the same `except`."""

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
    # What the uploader wrote under the film, clipped. Only a search result's screening reads it: it costs nothing extra,
    # since the details call that fills the rest of this is made for every result anyway.
    description: str = ""


class SourceError(Exception):
    """A film source could not answer. The loop leaves the archive as it was and tries again on the next pass."""


class SourceUnavailable(SourceError):
    """The source did not answer usefully — a network error, a 5xx, a document that would not parse."""


class SourceRefused(SourceUnavailable):
    """The source answered, and counted the call against its allowance, but the answer was a refusal or of no use. Unlike a
    call it never answered, asking again at once costs again."""


class RequestInvalid(SourceRefused):
    """The source says the request itself is wrong — a 400, a mistake of ours that no retry will cure. A topic asking it
    would pay for the same refusal every interval, so it is switched off instead of held."""


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

    @property
    def listing_cost(self) -> int:
        """One channel's latest films: the listing and the details call that follows it."""
        ...

    async def resolve_channel(self, reference: str) -> ChannelInfo: ...

    async def latest_videos(self, channel: ChannelInfo) -> list[VideoRef]: ...

    async def search(
        self, phrase: str, *, language: str, published_after: datetime | None, limit: int
    ) -> list[VideoRef]: ...

    async def video_details(self, video_ids: Sequence[str]) -> list[VideoRef]: ...


# --- transcripts ----------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TranscriptRequest:
    """What the transcriber is told about the film: enough to price it before asking, and to cut a long one."""

    video_id: str
    duration_seconds: int | None
    audio_language: str | None = None


@dataclass(frozen=True, slots=True)
class Transcript:
    """`text` is paragraphs, each opening with its time from the start of the film (`[MM:SS]`). `model` names the model
    that wrote it down."""

    text: str
    language: str
    automatic: bool
    provider: str
    simulated: bool = False
    model: str | None = None


@dataclass(frozen=True, slots=True)
class NoTranscript:
    """The provider answered, and it has no text for this film — private, cut off, nothing said. `charged` is whether
    asking cost anything, which the loop records either way: a miss that was billed is still billed."""

    provider: str
    reason: str
    charged: bool = False


@dataclass(frozen=True, slots=True)
class Blocked:
    """The provider did not let us in, or did not answer — a crowded model, a rate limit, a timeout, a bad key. Says
    nothing about the film, so the loop must not count it as one of the film's attempts."""

    provider: str
    reason: str


TranscriptResult = Transcript | NoTranscript | Blocked


class TranscriptProvider(Protocol):
    name: str
    unit: str

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
