"""The one place the three simulated providers agree on what is true: which films exist now, what day it is, what has been
spent today. Sharing it is the point — a film the source lists is a film the transcript provider knows about."""

from __future__ import annotations

import asyncio
import random
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from ..clock import Clock
from ..providers.base import Meter, VideoRef
from .scenario import Scenario, SimChannel, SimVideo


class World:
    def __init__(self, scenario: Scenario, clock: Clock, meter: Meter) -> None:
        self.scenario = scenario
        self.clock = clock
        self.meter = meter
        self.started_at = clock.now()
        self._videos = {video.video_id: video for video in scenario.videos}
        self._channels = {channel.channel_id: channel for channel in scenario.channels}
        self._spent: defaultdict[tuple[date, str], int] = defaultdict(int)
        self._fetches: defaultdict[str, int] = defaultdict(int)
        # job id -> (video id, ready at)
        self.jobs: dict[str, tuple[str, datetime]] = {}

    # --- what exists ------------------------------------------------------------------------------------------------

    def channel(self, channel_id: str) -> SimChannel | None:
        return self._channels.get(channel_id)

    def channel_by_handle(self, handle: str) -> SimChannel | None:
        wanted = handle.lower()
        return next((c for c in self._channels.values() if (c.handle or "").lower() == wanted), None)

    def video(self, video_id: str) -> SimVideo | None:
        return self._videos.get(video_id)

    def published_at(self, video: SimVideo) -> datetime:
        return self.started_at + timedelta(minutes=video.published_after_start_minutes)

    def visible(self, video: SimVideo) -> bool:
        """A film exists for the outside world from its publication on."""
        return self.published_at(video) <= self.clock.now()

    def live_status(self, video: SimVideo) -> str:
        if video.live_until_minutes is None:
            return "none"
        return "live" if self.clock.now() < self.started_at + timedelta(minutes=video.live_until_minutes) else "none"

    def ref(self, video: SimVideo) -> VideoRef:
        channel = self._channels[video.channel]
        return VideoRef(
            video_id=video.video_id,
            channel_id=channel.channel_id,
            channel_title=channel.title,
            title=video.title,
            published_at=self.published_at(video),
            duration_seconds=video.duration_seconds,
            live_status=self.live_status(video),
            simulated=True,
        )

    # --- what is spent ----------------------------------------------------------------------------------------------

    def today(self) -> date:
        return self.clock.now().astimezone(UTC).date()

    def spent_today(self, unit: str) -> int:
        return self._spent[(self.today(), unit)]

    def spend(self, provider: str, unit: str, amount: int, *, cap: int | None) -> bool:
        """Books `amount` and says whether the provider's own day allowed it. A refused call is booked all the same: a
        provider that says no still had to be asked."""
        self._spent[(self.today(), unit)] += amount
        self.meter.record(provider, unit, amount)
        return cap is None or self._spent[(self.today(), unit)] <= cap

    # --- what is random, and repeatably -----------------------------------------------------------------------------

    def roll(self, video_id: str) -> float:
        """A number in [0, 1) that depends only on the seed, the film and how many times it has been asked about — not on
        what else happened in between, so the same run refuses the same requests."""
        self._fetches[video_id] += 1
        return random.Random(f"{self.scenario.seed}:{video_id}:{self._fetches[video_id]}").random()

    async def lag(self, milliseconds: int) -> None:
        if milliseconds:
            await asyncio.sleep(milliseconds / 1000)
