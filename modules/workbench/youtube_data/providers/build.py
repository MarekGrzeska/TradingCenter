"""The providers a deployment is configured for, chosen by name. `None` for the analyser is a supported state and the
reason this is a function returning a value rather than a refusal: without a model the package still discovers and
transcribes, every reading stays empty, and `/state` says which of the two it is."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import httpx

from ..analysis import Analyser, OpenAIAnalyser
from ..clock import Clock, SimClock, SystemClock
from ..config import Settings
from ..screening import OpenAIScreener, Screener
from .base import Meter, TranscriptProvider, VideoSource
from .data_api import DataApiSource

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Providers:
    source: VideoSource
    transcriber: TranscriptProvider
    analyser: Analyser | None
    # Reads a search result's metadata, on the analyser's key, model and day; absent exactly where the analyser is.
    screener: Screener | None
    meter: Meter
    # The time everything that schedules must read: the wall clock, or the simulation's, which runs faster.
    clock: Clock

    async def aclose(self) -> None:
        close = getattr(self.transcriber, "aclose", None)
        if close is not None:
            await close()


def build(settings: Settings, http: httpx.AsyncClient) -> Providers:
    meter = Meter()

    # One world for every simulated provider, made only when one is chosen: a film the source lists is a film the
    # transcriber knows about, and both read the same clock.
    clock: Clock = SystemClock()
    world = None
    if settings.simulating:
        from ..sim import scenario
        from ..sim.world import World

        # Only a simulated source gets the fast clock: a real one would have its daily ceilings reset every hour.
        if settings.video_source == "sim":
            clock = SimClock(settings.sim_speed)
        chosen = Path(settings.sim_scenario) if settings.sim_scenario else None
        world = World(scenario.load(chosen), clock, meter)
        log.warning("simulating: films, transcripts or readings in this process are not real")

    source: VideoSource
    if settings.video_source == "sim" and world is not None:
        from ..sim.providers import SimSource

        source = SimSource(world)
    else:
        # The settings refused a start without the key, so it is here.
        source = DataApiSource(http, api_key=settings.data_api_key or "", meter=meter)

    transcriber: TranscriptProvider
    if settings.transcriber == "sim" and world is not None:
        from ..sim.providers import SimTranscriber

        transcriber = SimTranscriber(world)
    else:
        from . import gemini

        transcriber = gemini.GeminiTranscripts(
            # The settings refused a start without the key, so it is here.
            api_key=settings.gemini_api_key or "",
            model=settings.gemini_model,
            piece_seconds=settings.gemini_chunk_minutes * 60,
            meter=meter,
            timeout_seconds=settings.gemini_timeout_seconds,
        )

    analyser, screener = _model(settings, world)
    return Providers(
        source=source,
        transcriber=transcriber,
        analyser=analyser,
        screener=screener,
        meter=meter,
        clock=clock,
    )


def _model(settings: Settings, world) -> tuple[Analyser | None, Screener | None]:
    """The reader of films and the screener of search results: one key and one model, or neither."""
    if settings.analyser == "sim" and world is not None:
        from ..sim.providers import SimAnalyser, SimScreener

        return SimAnalyser(world), SimScreener(world)
    if not settings.model_configured:
        log.warning(
            "no model is configured — films will be discovered and transcribed and left unread, and search results unscreened"
        )
        return None, None
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
    return (
        OpenAIAnalyser(client, model=settings.analysis_model, max_chars=settings.analysis_max_chars),
        OpenAIScreener(client, model=settings.analysis_model),
    )
