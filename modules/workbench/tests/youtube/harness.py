"""A loop wired to the simulation, with a clock a test moves by hand."""

from __future__ import annotations

from datetime import timedelta

from youtube_data.alerts import Alerts
from youtube_data.analysis import Analyser
from youtube_data.clock import ManualClock
from youtube_data.config import Settings
from youtube_data.ingest import Ingest
from youtube_data.providers.base import Meter
from youtube_data.providers.build import Providers
from youtube_data.providers.chain import TranscriptChain
from youtube_data.sim import scenario as scenarios
from youtube_data.sim.providers import SimAnalyser, SimSource, SimTranscripts
from youtube_data.sim.scenario import Scenario
from youtube_data.sim.world import World

GOLD = "UCsimGoldPL0000000000000"
MARKETS = "UCsimMarketsEN0000000000"
CRYPTO = "UCsimCryptoPL00000000000"


def settings(**overrides) -> Settings:
    """A workstation's settings: the simulation is the default there."""
    return Settings(database_url="postgresql://localhost:5432/youtube", _env_file=None, **overrides)


class Rig:
    def __init__(
        self,
        pool,
        scenario: Scenario | None = None,
        *,
        analyser: Analyser | None | str = "sim",
        **overrides,
    ) -> None:
        self.pool = pool
        self.clock = ManualClock()
        self.meter = Meter()
        self.world = World(scenario or scenarios.load(), self.clock, self.meter)
        self.settings = settings(**overrides)
        self.providers = Providers(
            source=SimSource(self.world),
            transcripts=TranscriptChain([SimTranscripts(self.world)]),
            analyser=SimAnalyser(self.world) if analyser == "sim" else analyser,  # type: ignore[arg-type]
            meter=self.meter,
            clock=self.clock,
        )
        self.ingest = Ingest(pool, self.providers, self.settings)

    def announcing_to(self, gateway, *, destination: str = "operator") -> Alerts:
        """The loop, now told to announce through `gateway`, which is a recording one rather than Telegram."""
        alerts = Alerts(
            self.pool,
            gateway,
            destination=destination,
            min_score=self.settings.alert_min_impact_score,
            batch_limit=self.settings.announce_batch_limit,
            window=timedelta(hours=self.settings.alert_window_hours),
        )
        self.ingest = Ingest(self.pool, self.providers, self.settings, announce=alerts.run)
        return alerts

    async def tick(self) -> None:
        await self.ingest.tick()

    async def states(self) -> dict[str, str]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT video_id, state FROM videos")
        return {row["video_id"]: row["state"] for row in rows}

    async def row(self, video_id: str):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow("SELECT * FROM videos WHERE video_id = $1", video_id)

    async def used(self, provider: str, unit: str) -> int:
        async with self.pool.acquire() as conn:
            value = await conn.fetchval(
                "SELECT COALESCE(sum(amount), 0) FROM usage WHERE provider = $1 AND unit = $2", provider, unit
            )
        return int(value)
