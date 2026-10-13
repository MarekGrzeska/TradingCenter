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

from youtube_data.providers.base import Blocked, Meter, NoTranscript, Transcript, TranscriptRequest
from youtube_data.providers.chain import ChainAnswer, Deferred, TranscriptChain
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


def captions(*lines: tuple[float, str], generated: bool = True, language: str = "pl"):
    return SimpleNamespace(
        snippets=[SimpleNamespace(text=text, start=start, duration=1.0) for start, text in lines],
        language_code=language,
        is_generated=generated,
    )


def error(cls):
    """The library's errors carry a video id and build their own message; the tests want only their type."""
    instance = cls.__new__(cls)
    Exception.__init__(instance, "raised by the test")
    return instance


def request(video_id: str = "v1", *, audio: str | None = None, duration: int | None = 600) -> TranscriptRequest:
    return TranscriptRequest.for_film(video_id, duration_seconds=duration, audio_language=audio, fallback=("pl", "en"))


async def test_captions_become_paragraphs_stamped_with_their_time_language_and_kind() -> None:
    meter = Meter()
    lines = captions((0.0, "Dzień "), (4.2, " dobry"), (12.0, ""), (31.5, "drugi\nakapit"), (3725.0, "po godzinie"))
    provider = DirectTranscripts(meter, api=FakeApi(lines))

    result = await provider.fetch(request())

    assert result == Transcript(
        text="[00:00] Dzień dobry\n[00:31] drugi akapit\n[1:02:05] po godzinie",
        language="pl",
        automatic=True,
        provider="direct",
    )
    assert meter.drain() == {("direct", "requests"): 1}


async def test_captions_are_asked_for_in_the_films_own_language_alone_when_it_is_known() -> None:
    """Captions in another language are a translation: a Polish film's English captions are not the film."""
    api = FakeApi(error(NoTranscriptFound))

    await DirectTranscripts(Meter(), api=api).fetch(request(audio="pl"))
    await DirectTranscripts(Meter(), api=api).fetch(request(audio=None))

    assert [languages for _, languages in api.asked] == [["pl"], ["pl", "en"]]


@pytest.mark.parametrize("cls", [TranscriptsDisabled, NoTranscriptFound, VideoUnavailable])
async def test_a_film_with_nothing_to_read_has_no_transcript(cls) -> None:
    result = await DirectTranscripts(Meter(), api=FakeApi(error(cls))).fetch(request())

    assert isinstance(result, NoTranscript)
    assert result.reason == cls.__name__


@pytest.mark.parametrize("cls", [IpBlocked, PoTokenRequired])
async def test_being_refused_is_blocked_and_never_no_transcript(cls) -> None:
    """From a datacenter address every film would otherwise read as one without captions."""
    result = await DirectTranscripts(Meter(), api=FakeApi(error(cls))).fetch(request())

    assert isinstance(result, Blocked)


async def test_captions_that_are_only_silence_are_not_a_transcript() -> None:
    result = await DirectTranscripts(Meter(), api=FakeApi(captions((0.0, ""), (1.0, "  ")))).fetch(request())

    assert isinstance(result, NoTranscript)


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

    result = await DirectTranscripts(meter, api=api).fetch(request())  # type: ignore[arg-type]

    assert isinstance(result, Blocked)
    assert meter.drain() == {("direct", "requests"): 1}


# --- the chain ------------------------------------------------------------------------------------------------------


class Scripted:
    def __init__(self, name: str, answer, *, listens: bool = False) -> None:
        self.name = name
        self.unit = "requests"
        self.listens = listens
        self.answer = answer
        self.asked = 0

    def price(self, request) -> int:
        return 1

    async def fetch(self, request):
        self.asked += 1
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def text(provider: str) -> Transcript:
    return Transcript(text="[00:00] words", language="en", automatic=True, provider=provider)


async def test_the_next_provider_is_tried_when_the_one_before_did_not_let_us_in_and_the_refusal_is_kept() -> None:
    first = Scripted("first", Blocked("first", "IpBlocked"))
    second = Scripted("second", text("second"))

    answer = await TranscriptChain([first, second]).fetch(request())

    assert answer == ChainAnswer(text("second"), (Blocked("first", "IpBlocked"),))
    assert (first.asked, second.asked) == (1, 1)


async def test_no_captions_goes_on_to_the_provider_that_listens_and_past_any_other_captions_provider() -> None:
    missed = NoTranscript("captions", "TranscriptsDisabled")
    captions_a = Scripted("captions", missed)
    captions_b = Scripted("more-captions", text("more-captions"))
    listener = Scripted("gemini", text("gemini"), listens=True)

    answer = await TranscriptChain([captions_a, captions_b, listener]).fetch(request())

    assert answer == ChainAnswer(text("gemini"), (missed,))
    assert captions_b.asked == 0


async def test_with_nobody_who_listens_no_captions_is_the_films_answer_and_nobody_else_is_asked() -> None:
    first = Scripted("first", NoTranscript("first", "TranscriptsDisabled"))
    second = Scripted("second", text("second"))

    answer = await TranscriptChain([first, second]).fetch(request())

    assert answer.result == NoTranscript("first", "TranscriptsDisabled")
    assert second.asked == 0


async def test_a_listener_that_hears_nothing_is_the_films_answer() -> None:
    heard_nothing = NoTranscript("gemini", "private film")
    chain = TranscriptChain([Scripted("captions", NoTranscript("captions", "none")), Scripted("gemini", heard_nothing, listens=True)])

    assert (await chain.fetch(request())).result == heard_nothing


async def test_a_listener_that_refuses_after_no_captions_is_a_refusal_not_a_miss() -> None:
    """A rate-limited model says nothing about the film: the film must keep its attempts."""
    chain = TranscriptChain(
        [Scripted("captions", NoTranscript("captions", "none")), Scripted("gemini", Blocked("gemini", "429"), listens=True)]
    )

    answer = await chain.fetch(request())

    assert answer.result == Blocked("gemini", "429")
    assert answer.passed == (NoTranscript("captions", "none"),)


async def test_a_listener_left_out_after_no_captions_defers_the_film() -> None:
    chain = TranscriptChain(
        [Scripted("captions", NoTranscript("captions", "none")), Scripted("gemini", text("gemini"), listens=True)]
    )

    answer = await chain.fetch(request(), only={"captions"})

    assert isinstance(answer.result, Deferred)


async def test_nobody_left_to_ask_is_deferred_and_every_one_blocked_answers_with_the_last_refusal() -> None:
    chain = TranscriptChain([Scripted("a", Blocked("a", "one")), Scripted("b", Blocked("b", "two"))])

    assert await chain.fetch(request()) == ChainAnswer(Blocked("b", "two"), (Blocked("a", "one"),))
    assert isinstance((await chain.fetch(request(), only=())).result, Deferred)
    assert isinstance((await TranscriptChain([]).fetch(request())).result, Deferred)


async def test_a_provider_that_raises_is_passed_over_like_one_that_refused() -> None:
    after = DirectTranscripts(Meter(), api=FakeApi(captions((0.0, "słowa"))))

    answer = await TranscriptChain([Scripted("broken", RuntimeError("an adapter's own bug")), after]).fetch(request())

    assert isinstance(answer.result, Transcript) and answer.result.provider == "direct"
    assert isinstance(answer.passed[0], Blocked)
