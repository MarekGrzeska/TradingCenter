"""Transcripts written down by Gemini, which is handed the film's address and listens to it — the official Gemini API
reads a public YouTube film by its URL, with no captions needed and no scraping, from the cloud as from home. The way the
operator's own `yt-transkrypcje` skill does it, moved into the loop: a long film in pieces, a verbatim prompt, times
brought back to the start of the film.

What it costs is seconds of film, which is also how Google limits the free tier (eight hours a day), so that is the
unit the day's ceiling counts; the tokens are written down beside it, because they are what a paid key is billed."""

from __future__ import annotations

import re
from typing import Any

import httpx
from google import genai
from google.genai import errors, types

from .base import (
    Blocked,
    Meter,
    NoTranscript,
    Transcript,
    TranscriptRequest,
    TranscriptResult,
    stamp,
)

VIDEO_SECONDS = "video_seconds"
TOKENS = "tokens"

PROMPT = """You are a professional transcriber. Produce a COMPLETE, VERBATIM transcript of the speech in this video.

Rules:
- Write in exactly the language(s) spoken in the video. Do NOT translate.
- Do not summarize, skip, or paraphrase anything. No introduction or commentary.
- Start every paragraph (every 20-40 seconds or on speaker change) with a timestamp in square brackets: [MM:SS] or [H:MM:SS].
- When speakers can be told apart, put the speaker after the timestamp, e.g. "[03:12] Anna: ...". Use names only if they are said or shown in the video; otherwise use neutral labels like "Speaker 1".
- Do NOT mark background music or sounds. Only a silent/music-only stretch longer than 10 seconds may be marked once, briefly, e.g. [music].
- Output only the transcript."""

MAX_OUTPUT_TOKENS = 32_768

# A film this much longer than a piece is still asked about whole: 33 minutes is one call, not 30 and 3.
WHOLE_UP_TO = 1.2

_STAMP = re.compile(r"^\s*\[(?:(\d+):)?(\d{1,2}):(\d{2})\]\s*(.*)$")

# Words in a 400 or 404 that make it about our key or our model rather than the film: Google answers a bad key with a
# 400, and a model name it does not know with a 404 — read as "this film", either would give every film up.
_ABOUT_US = ("api key", "api_key", "model")


def pieces(duration: int, piece: int) -> list[tuple[int, int | None]]:
    """`(start, end)` seconds of each call; `end` is `None` for the film whole."""
    if duration <= piece * WHOLE_UP_TO:
        return [(0, None)]
    return [(start, min(start + piece, duration)) for start in range(0, duration, piece)]


def parse(text: str, offset: int) -> list[tuple[int, str]]:
    """Gemini's `[MM:SS] …` paragraphs as `(seconds from the start of the film, text)`. Asked about a piece, Gemini
    counts time sometimes from the piece and sometimes from the film; the first stamp decides — nearer zero than the
    offset, the piece's clock, so the offset is added."""
    found: list[list[Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        match = _STAMP.match(line)
        if match:
            hours, minutes, seconds, rest = match.groups()
            found.append([int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds), rest.strip()])
        elif found:
            found[-1][1] = f"{found[-1][1]} {line.strip()}".strip()
        else:
            found.append([0, line.strip()])
    if offset and found:
        first = found[0][0]
        if abs(first) < abs(first - offset):
            for item in found:
                item[0] += offset
    return [(at, said) for at, said in found if said]


def _tokens(response: Any) -> int:
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return 0
    return sum(
        getattr(usage, name, None) or 0
        for name in ("prompt_token_count", "candidates_token_count", "thoughts_token_count")
    )


def _finish(response: Any) -> str | None:
    candidates = getattr(response, "candidates", None) or []
    reason = getattr(candidates[0], "finish_reason", None) if candidates else None
    return getattr(reason, "name", None) if reason is not None else None


def _text(response: Any) -> str:
    try:
        return (response.text or "").strip()
    except (ValueError, AttributeError):
        # A candidate stopped for safety carries no text part, and the SDK says so by raising.
        return ""


class GeminiTranscripts:
    name = "gemini"
    unit = VIDEO_SECONDS

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        piece_seconds: int,
        meter: Meter,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        # Our own client under the SDK's: one transport whatever else is installed, closed with the provider, and one a
        # test can stand in for. The SDK sends the key as `x-goog-api-key`, never in the address.
        self._http = httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(timeout_seconds, connect=10.0))
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=int(timeout_seconds * 1000), httpx_async_client=self._http),
        )
        self._model = model
        self._piece = piece_seconds
        self._meter = meter
        self._config = types.GenerateContentConfig(
            media_resolution=types.MediaResolution.MEDIA_RESOLUTION_LOW,
            temperature=0.2,
            # Measured on a 29-minute Polish film (13 October 2026): without it the answer is cut off at the model's
            # default, long before the film ends. A quarter of an hour of speech is a few thousand tokens.
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )

    def price(self, request: TranscriptRequest) -> int:
        return request.duration_seconds or 0

    async def fetch(self, request: TranscriptRequest) -> TranscriptResult:
        if not request.duration_seconds:
            # A premiere that has not run: nothing to price, nothing to cut. The source fills it in on a later pass.
            return NoTranscript(self.name, "the film's length is not known yet")
        url = f"https://www.youtube.com/watch?v={request.video_id}"
        heard: list[tuple[int, str]] = []
        for start, end in pieces(request.duration_seconds, self._piece):
            try:
                response = await self._client.aio.models.generate_content(
                    model=self._model, contents=_contents(url, start, end), config=self._config
                )
            except errors.APIError as err:
                return self._refusal(err)
            except Exception as err:  # noqa: BLE001 - a timeout or a network error says nothing about the film
                return Blocked(self.name, f"Gemini did not answer: {type(err).__name__}")

            # Billed once answered, whatever the answer is worth to us.
            self._meter.record(self.name, VIDEO_SECONDS, (end or request.duration_seconds) - start)
            self._meter.record(self.name, TOKENS, _tokens(response))
            text, reason = _text(response), _finish(response)
            if reason == "MAX_TOKENS":
                return NoTranscript(
                    self.name, "Gemini's answer was cut off — a smaller GEMINI_CHUNK_MINUTES would fit", charged=True
                )
            if not text:
                return NoTranscript(self.name, f"Gemini wrote nothing down (finish reason {reason})", charged=True)
            heard += parse(text, start)

        if not heard:
            return NoTranscript(self.name, "Gemini heard nothing to write down", charged=True)
        return Transcript(
            text="\n".join(f"{stamp(at)} {said}" for at, said in heard),
            # BCP 47's "undetermined": the uploader did not say, and the model is not asked to.
            language=request.audio_language or "und",
            automatic=True,
            provider=self.name,
            model=self._model,
        )

    def _refusal(self, err: errors.APIError) -> TranscriptResult:
        # The code and status only: the details are Google's text, and nothing from a response belongs in a log whole.
        said = f"{err.code} {err.status or ''}".strip()
        message = f"{err.message or ''} {err.status or ''}".lower()
        if err.code in (400, 404) and not any(word in message for word in _ABOUT_US):
            return NoTranscript(self.name, f"Gemini cannot watch this film ({said})")
        return Blocked(self.name, f"Gemini refused ({said})")

    async def aclose(self) -> None:
        await self._client.aio.aclose()
        await self._http.aclose()


def _contents(url: str, start: int, end: int | None) -> types.Content:
    clip = None if end is None else types.VideoMetadata(start_offset=f"{start}s", end_offset=f"{end}s")
    return types.Content(
        role="user",
        parts=[
            types.Part(file_data=types.FileData(file_uri=url), video_metadata=clip),
            types.Part(text=PROMPT),
        ],
    )

