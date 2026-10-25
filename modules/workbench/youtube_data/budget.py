"""Each provider's day. The loop counts what it spends in the provider's own unit and stops asking at a ceiling of its own
setting, rather than trusting the provider's dashboard to say no — a dashboard says it after the money is gone, and the
YouTube Data API says it as a 403 that costs a unit to receive."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

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


def channels_reserve(channels: int, listing_cost: int, *, now: datetime, interval_seconds: float) -> int:
    """What the followed channels will still spend before midnight UTC, one listing each per pass. Topics search only beyond
    it: on 23 and 24 October 2026 eight topics spent the whole day on refusals, and the one followed channel went unlisted."""
    midnight = datetime.combine(utc_day(now) + timedelta(days=1), time.min, tzinfo=UTC)
    passes = math.ceil((midnight - now).total_seconds() / max(interval_seconds, 1))
    return channels * listing_cost * passes


async def remaining(conn: Conn, ceiling: Ceiling, *, day: date) -> int:
    """What is left of this provider's day: never below zero, so a caller can compare it with a price."""
    spent = (await store.usage_on(conn, day)).get((ceiling.provider, ceiling.unit), 0)
    return max(0, ceiling.limit - spent)
