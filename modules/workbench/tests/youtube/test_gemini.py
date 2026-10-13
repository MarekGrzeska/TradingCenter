"""The provider that listens: what it asks Gemini for, what it makes of the answers and what it counts — through the real
SDK over a stood-in transport, so the request is the one Google would get."""

from __future__ import annotations

import json

import httpx
import pytest

from youtube_data.providers.base import Blocked, Meter, NoTranscript, Transcript, TranscriptRequest
from youtube_data.providers.gemini import GeminiTranscripts, parse, pieces

KEY = "secret-gemini-key"


def answer(text: str | None, *, finish: str = "STOP", prompt: int = 1000, output: int = 200) -> httpx.Response:
    parts = [] if text is None else [{"text": text}]
    return httpx.Response(
        200,
        json={
            "candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": finish}],
            "usageMetadata": {"promptTokenCount": prompt, "candidatesTokenCount": output},
        },
    )


def refusal(code: int, message: str, status: str) -> httpx.Response:
    return httpx.Response(code, json={"error": {"code": code, "message": message, "status": status}})


class Google:
    """Answers each request in turn and keeps what it was asked."""

    def __init__(self, *answers: httpx.Response | Exception) -> None:
        self._answers = list(answers)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        found = self._answers.pop(0)
        if isinstance(found, Exception):
            raise found
        return found

    def then(self, *answers: httpx.Response | Exception) -> None:
        self._answers.extend(answers)

    def bodies(self) -> list[dict]:
        return [json.loads(request.content) for request in self.requests]


def provider(google: Google, meter: Meter | None = None, *, piece_minutes: int = 30) -> GeminiTranscripts:
    return GeminiTranscripts(
        api_key=KEY,
        model="gemini-test",
        piece_seconds=piece_minutes * 60,
        meter=meter or Meter(),
        timeout_seconds=5,
        transport=httpx.MockTransport(google),
    )


def request(duration: int | None = 1200, audio: str | None = "pl") -> TranscriptRequest:
    return TranscriptRequest("dQw4w9WgXcQ", duration, audio)


async def test_a_film_is_written_down_from_its_address_and_counted_in_seconds_and_tokens() -> None:
    google = Google(answer("[00:00] Anna: Dzień dobry.\n\n[00:31] Anna: O złocie\ndziś."))
    meter = Meter()

    result = await provider(google, meter).fetch(request())

    assert result == Transcript(
        text="[00:00] Anna: Dzień dobry.\n[00:31] Anna: O złocie dziś.",
        language="pl",
        automatic=True,
        provider="gemini",
        model="gemini-test",
    )
    (body,) = google.bodies()
    video = body["contents"][0]["parts"][0]
    assert video["fileData"]["file_uri"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert "videoMetadata" not in video
    assert body["generationConfig"]["mediaResolution"] == "MEDIA_RESOLUTION_LOW"
    assert meter.drain() == {("gemini", "video_seconds"): 1200, ("gemini", "tokens"): 1200}


async def test_the_key_travels_in_a_header_and_never_in_the_address() -> None:
    google = Google(answer("[00:00] hello"))

    await provider(google).fetch(request())

    (sent,) = google.requests
    assert sent.headers["x-goog-api-key"] == KEY
    assert KEY not in str(sent.url)


async def test_an_hour_is_asked_about_in_two_pieces_and_the_second_reads_from_thirty_minutes() -> None:
    """Gemini counts the second piece's time from the piece here; the first stamp decides it, and the offset is added."""
    google = Google(answer("[00:00] start"), answer("[00:05] po przerwie\n[1:10] dalej"))

    result = await provider(google).fetch(request(duration=3600))

    assert isinstance(result, Transcript)
    assert result.text == "[00:00] start\n[30:05] po przerwie\n[31:10] dalej"
    clips = [body["contents"][0]["parts"][0]["videoMetadata"] for body in google.bodies()]
    assert [(clip["start_offset"], clip["end_offset"]) for clip in clips] == [("0s", "1800s"), ("1800s", "3600s")]


def test_a_piece_already_counted_from_the_film_is_left_as_it_is() -> None:
    assert parse("[30:02] już od początku filmu", offset=1800) == [(1802, "już od początku filmu")]


def test_a_film_a_little_longer_than_a_piece_is_one_call() -> None:
    assert pieces(33 * 60, 30 * 60) == [(0, None)]
    assert pieces(37 * 60, 30 * 60) == [(0, 1800), (1800, 2220)]


@pytest.mark.parametrize(
    ("reply", "kind"),
    [
        (refusal(429, "Resource has been exhausted", "RESOURCE_EXHAUSTED"), Blocked),
        (refusal(503, "The model is overloaded", "UNAVAILABLE"), Blocked),
        (refusal(403, "Permission denied", "PERMISSION_DENIED"), Blocked),
        (refusal(400, "API key not valid. Please pass a valid API key.", "INVALID_ARGUMENT"), Blocked),
        (refusal(404, "models/gemini-nope is not found", "NOT_FOUND"), Blocked),
        (httpx.ConnectError("refused"), Blocked),
        (refusal(400, "Cannot fetch content from the provided URL", "INVALID_ARGUMENT"), NoTranscript),
    ],
)
async def test_a_refusal_about_us_is_blocked_and_one_about_the_film_is_no_transcript(reply, kind) -> None:
    """A bad key answers 400 and an unknown model 404: read as "this film", every film would be given up."""
    meter = Meter()
    google = Google(reply)

    result = await provider(google, meter).fetch(request())

    assert isinstance(result, kind)
    # Asked once: the loop decides when to ask again, not the SDK behind its back.
    assert len(google.requests) == 1
    assert KEY not in result.reason
    assert meter.drain() == {}
    if isinstance(result, NoTranscript):
        assert result.charged is False


@pytest.mark.parametrize(
    ("reply", "reason"),
    [(answer("[00:00] urwane w poł", finish="MAX_TOKENS"), "cut off"), (answer(None, finish="SAFETY"), "SAFETY")],
)
async def test_an_answer_cut_off_or_withheld_is_no_transcript_that_was_paid_for(reply, reason) -> None:
    meter = Meter()

    result = await provider(Google(reply), meter).fetch(request())

    assert isinstance(result, NoTranscript) and result.charged
    assert reason in result.reason
    assert meter.drain()[("gemini", "video_seconds")] == 1200


async def test_a_film_whose_length_is_not_known_is_neither_priced_nor_asked_about() -> None:
    google = Google()
    listener = provider(google)

    result = await listener.fetch(request(duration=None))

    assert isinstance(result, NoTranscript) and not result.charged
    assert google.requests == []
    assert listener.price(request(duration=754)) == 754


async def test_a_film_whose_language_nobody_declared_is_undetermined() -> None:
    result = await provider(Google(answer("[00:00] hello"))).fetch(request(audio=None))

    assert isinstance(result, Transcript) and result.language == "und"


async def test_pieces_already_written_are_not_paid_for_again_when_a_later_one_is_refused() -> None:
    """A film of two pieces whose second is refused with a 503 used to be asked again from its first minute, each try."""
    google = Google(answer("[00:00] pierwsza część"), refusal(503, "The model is overloaded", "UNAVAILABLE"))
    meter = Meter()
    listener = provider(google, meter, piece_minutes=15)
    film = request(duration=1500)  # two pieces: 0-900 and 900-1500

    first = await listener.fetch(film)
    assert isinstance(first, Blocked)
    assert meter.drain()[("gemini", "video_seconds")] == 900, "the first piece was answered and paid for"

    google.then(answer("[00:10] druga część"))
    second = await listener.fetch(film)

    assert isinstance(second, Transcript)
    assert second.text == "[00:00] pierwsza część\n[15:10] druga część"
    assert len(google.requests) == 3, "the first piece was not asked a second time"
    assert meter.drain()[("gemini", "video_seconds")] == 600, "only the second piece was paid for"
