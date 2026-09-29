"""The providers a deployment is configured for, chosen by name. `None` for the analyser is a supported state and the
reason this is a function returning a value rather than a refusal: without a model the package still discovers and
transcribes, every reading stays empty, and `/state` says which of the two it is."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from ..analysis import Analyser, OpenAIAnalyser
from ..config import Settings
from .base import Meter, TranscriptProvider, VideoSource
from .chain import TranscriptChain
from .data_api import DataApiSource
from .direct import DirectTranscripts
from .rss import RssSource

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Providers:
    source: VideoSource
    transcripts: TranscriptChain
    analyser: Analyser | None
    meter: Meter


def build(settings: Settings, http: httpx.AsyncClient) -> Providers:
    meter = Meter()

    source: VideoSource
    if settings.video_source == "data_api":
        # The settings refused a start without the key, so it is here.
        source = DataApiSource(http, api_key=settings.data_api_key or "", meter=meter)
    else:
        source = RssSource(http, meter=meter)

    transcripts: list[TranscriptProvider] = []
    for name in settings.transcript_provider_names:
        if name == "direct":
            transcripts.append(DirectTranscripts(meter))

    return Providers(
        source=source,
        transcripts=TranscriptChain(transcripts),
        analyser=_analyser(settings),
        meter=meter,
    )


def _analyser(settings: Settings) -> Analyser | None:
    if not settings.model_configured:
        log.warning("no model is configured — films will be discovered and transcribed, and left unread")
        return None
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
    return OpenAIAnalyser(client, model=settings.analysis_model, max_chars=settings.analysis_max_chars)
