"""The transcript providers: what `direct` makes of the library's answers, and how the chain moves between providers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from youtube_transcript_api._errors import (
    IpBlocked,
    NoTranscriptFound,
    PoTokenRequired,
    TranscriptsDisabled,
    VideoUnavailable,
)

from youtube_data.providers.base import Blocked, Meter, NoTranscript, Pending, Transcript
from youtube_data.providers.chain import TranscriptChain
from youtube_data.providers.direct import DirectTranscripts


class FakeApi:
    """Stands where `YouTubeTranscriptApi` does: raises what it is told to, or returns snippets."""

    def __init__(self, outcome) -> None:
        self._outcome = outcome
        self.asked: list[tuple[str, list[str]]] = []

    def fetch(self, video_id, languages):
        self.asked.append((video_id, languages))
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


def captions(*texts: str, generated: bool = True, language: str = "pl"):
    return SimpleNamespace(
        snippets=[SimpleNamespace(text=text, start=0.0, duration=1.0) for text in texts],
        language_code=language,
        is_generated=generated,
    )


def error(cls):
    """The library's errors carry a video id and build their own message; the tests want only their type."""
    instance = cls.__new__(cls)
    Exception.__init__(instance, "raised by the test")
    return instance


async def test_captions_become_one_text_stamped_with_their_language_and_kind() -> None:
    meter = Meter()
    provider = DirectTranscripts(meter, api=FakeApi(captions("Dzień ", " dobry", "", generated=False)))

    result = await provider.fetch("v1", ["pl", "en"])

    assert result == Transcript(text="Dzień dobry", language="pl", automatic=False, provider="direct")
    assert meter.drain() == {("direct", "requests"): 1}


@pytest.mark.parametrize("cls", [TranscriptsDisabled, NoTranscriptFound, VideoUnavailable])
async def test_a_film_with_nothing_to_read_has_no_transcript(cls) -> None:
    result = await DirectTranscripts(Meter(), api=FakeApi(error(cls))).fetch("v1", ["en"])

    assert isinstance(result, NoTranscript)
    assert result.reason == cls.__name__


@pytest.mark.parametrize("cls", [IpBlocked, PoTokenRequired])
async def test_being_refused_is_blocked_and_never_no_transcript(cls) -> None:
    """From a datacenter address every film would otherwise read as one without captions."""
    result = await DirectTranscripts(Meter(), api=FakeApi(error(cls))).fetch("v1", ["en"])

    assert isinstance(result, Blocked)


async def test_captions_that_are_only_silence_are_not_a_transcript() -> None:
    result = await DirectTranscripts(Meter(), api=FakeApi(captions("", "  "))).fetch("v1", ["en"])

    assert isinstance(result, NoTranscript)


class Scripted:
    def __init__(self, name: str, answer) -> None:
        self.name = name
        self.answer = answer
        self.asked = 0

    async def fetch(self, video_id, languages):
        self.asked += 1
        return self.answer

    async def poll(self, job_id):
        return self.answer


TEXT = Transcript(text="words", language="en", automatic=True, provider="second")


async def test_the_next_provider_is_tried_when_the_one_before_did_not_let_us_in() -> None:
    first = Scripted("first", Blocked("first", "IpBlocked"))
    second = Scripted("second", TEXT)

    assert await TranscriptChain([first, second]).fetch("v1", ["en"]) == TEXT
    assert (first.asked, second.asked) == (1, 1)


async def test_a_film_with_no_captions_is_not_asked_about_twice() -> None:
    first = Scripted("first", NoTranscript("first", "TranscriptsDisabled"))
    second = Scripted("second", TEXT)

    result = await TranscriptChain([first, second]).fetch("v1", ["en"])

    assert isinstance(result, NoTranscript)
    assert second.asked == 0


async def test_every_provider_blocked_answers_with_the_last_refusal() -> None:
    chain = TranscriptChain([Scripted("a", Blocked("a", "one")), Scripted("b", Blocked("b", "two"))])

    assert await chain.fetch("v1", ["en"]) == Blocked("b", "two")
    assert await TranscriptChain([]).fetch("v1", ["en"]) == Blocked("chain", "no transcript provider is configured")


async def test_a_job_is_polled_at_the_provider_that_took_it() -> None:
    paid = Scripted("paid", Pending("paid", "job-1"))
    chain = TranscriptChain([Scripted("free", Blocked("free", "x")), paid])

    assert await chain.fetch("v1", ["en"]) == Pending("paid", "job-1")
    assert await chain.poll("paid", "job-1") == Pending("paid", "job-1")
    assert isinstance(await chain.poll("gone", "job-1"), Blocked)


@pytest.mark.parametrize("raised", [ConnectionError("refused"), TimeoutError()])
async def test_a_way_in_that_breaks_is_blocked_and_counted_not_raised(raised: Exception, monkeypatch) -> None:
    """`requests` wraps only HTTP errors in the library's type; a dropped connection, or one that never answers, must
    still read as *blocked* — raised, it would end the whole transcription step and never reach the next provider."""
    if isinstance(raised, TimeoutError):
        monkeypatch.setattr("youtube_data.providers.direct.FETCH_TIMEOUT_SECONDS", 0.01)

        class Hangs:
            def fetch(self, video_id, languages):
                import time

                time.sleep(0.2)

        api = Hangs()
    else:
        api = FakeApi(raised)
    meter = Meter()

    result = await DirectTranscripts(meter, api=api).fetch("v1", ["pl"])  # type: ignore[arg-type]

    assert isinstance(result, Blocked)
    assert meter.drain() == {("direct", "requests"): 1}


async def test_a_provider_that_raises_is_passed_over_like_one_that_refused() -> None:
    class Raises:
        name = "broken"
        unit = "requests"

        async def fetch(self, video_id, languages):
            raise RuntimeError("an adapter's own bug")

        async def poll(self, job_id):
            raise AssertionError("never polled")

    after = DirectTranscripts(Meter(), api=FakeApi(captions("słowa")))

    result = await TranscriptChain([Raises(), after]).fetch("v1", ["pl"])

    assert isinstance(result, Transcript) and result.provider == "direct"
