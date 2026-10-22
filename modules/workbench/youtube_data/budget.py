"""Each provider's day. The loop counts what it spends in the provider's own unit and stops asking at a ceiling of its own
setting, rather than trusting the provider's dashboard to say no — a dashboard says it after the money is gone, and the
YouTube Data API says it as a 403 that costs a unit to receive."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from tc_runtime.db import Conn

from . import store
from .config import Settings
from .providers.base import TranscriptProvider
from .providers.build import Providers

# The model is billed in tokens, and the one row for it: every analyser is "the analyser" to the loop.
ANALYSER = "analyser"
TOKENS = "tokens"


@dataclass(frozen=True, slots=True)
class Ceiling:
    provider: str
    unit: str
    limit: int


def transcript_ceiling(settings: Settings, provider: TranscriptProvider) -> Ceiling:
    """The transcriber is paid in seconds of film, the unit Google limits it in."""
    return Ceiling(provider.name, provider.unit, settings.gemini_daily_video_seconds)


def ceilings(settings: Settings, providers: Providers) -> list[Ceiling]:
    found = [Ceiling(providers.source.name, providers.source.unit, settings.daily_source_units)]
    found.append(transcript_ceiling(settings, providers.transcriber))
    if providers.analyser is not None:
        found.append(Ceiling(ANALYSER, TOKENS, settings.daily_token_limit))
    return found


def utc_day(moment: datetime) -> date:
    return moment.astimezone(UTC).date()


async def remaining(conn: Conn, ceiling: Ceiling, *, day: date) -> int:
    """What is left of this provider's day: never below zero, so a caller can compare it with a price."""
    spent = (await store.usage_on(conn, day)).get((ceiling.provider, ceiling.unit), 0)
    return max(0, ceiling.limit - spent)
