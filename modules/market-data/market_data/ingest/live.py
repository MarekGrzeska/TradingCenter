"""One pair's subscription, kept alive for as long as the operator wants it. The gap-closing is inside
the loop: a dropped subscription is also a stretch nobody was listening for."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ..errors import GatewayError
from ..gateway import CandleUpdate, FeedFailure, FeedState, FeedStatus, subscribe
from ..gateway import GatewayHistory as _GatewayHistory
from ..models import Candle, Resolution
from ..periods import period_length
from ..store import commit_candles
from .backfill import FillOutcome, fill_gap

log = logging.getLogger(__name__)


@dataclass
class Backoff:
    """How long to wait before trying the feed again. Growing, because a tight retry loop turns one
    outage into a second problem; capped, because a feed back after an hour should be picked up in a minute."""

    first: float = 1.0
    cap: float = 60.0
    factor: float = 2.0
    _current: float = field(default=0.0, init=False)

    def next_delay(self) -> float:
        self._current = self.first if self._current == 0 else min(self._current * self.factor, self.cap)
        return self._current

    def reset(self) -> None:
        """Called once a subscription actually produces something. On connection alone would be
        wrong: a gateway that accepts a socket and drops it would retry in a hot loop."""
        self._current = 0.0


@dataclass
class PairIngest:
    """Everything one pair's worth of ingest needs, and nothing about the others."""

    pool: object
    history: _GatewayHistory
    stream_url: str
    symbol: str
    resolution: Resolution
    default_bars: int
    still_tracked: Callable[[], Awaitable[bool]]
    gateway_api_key: str
    limiter: object | None = None
    # Where candles go instead of straight to storage. The contract layer supplies one that publishes
    # and stores inside the same hold, so a candle is never in both a snapshot and the change after it.
    sink: Callable[[Candle], Awaitable[None]] | None = None
    # Injected so the tests can supply a feed and a clock. In the process, these are the
    # real ones.
    subscribe_to: Callable = subscribe
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    backoff: Backoff = field(default_factory=Backoff)

    async def run(self) -> None:
        """Collect this pair until it stops being tracked. Closing the gap is inside the guard: it
        used to fail outside one, which ended the loop and collection until a restart."""
        while await self.still_tracked():
            try:
                await self._close_gap()

                await self._listen()
            except GatewayError as err:
                log.warning("%s %s: feed failed — %s", self.symbol, self.resolution.value, err)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("%s %s: feed raised", self.symbol, self.resolution.value)

            if not await self.still_tracked():
                return
            delay = self.backoff.next_delay()
            log.info(
                "%s %s: feed ended, retrying in %.0fs",
                self.symbol,
                self.resolution.value,
                delay,
            )
            await self.sleep(delay)

    async def _close_gap(self) -> FillOutcome:
        return await fill_gap(
            self.pool,
            self.history,
            self.symbol,
            self.resolution,
            default_bars=self.default_bars,
            limiter=self.limiter,
        )

    async def _listen(self) -> None:
        async with self.subscribe_to(
            self.stream_url, self.symbol, self.resolution, self.gateway_api_key
        ) as messages:
            async for message in messages:
                if isinstance(message, CandleUpdate):
                    self.backoff.reset()
                    await self._deliver(message.candle)
                elif isinstance(message, FeedStatus):
                    if message.state is FeedState.CONNECTED:
                        self.backoff.reset()
                elif isinstance(message, FeedFailure):
                    # The gateway reporting its own trouble, most often a provider reconnect — not
                    # fatal. But that stretch is one nobody listened for, so the gap is closed here.
                    log.warning(
                        "%s %s: gateway reported %s — closing the gap it left",
                        self.symbol,
                        self.resolution.value,
                        message.message,
                    )
                    await self._close_gap()

                if not await self.still_tracked():
                    return

    async def _deliver(self, candle) -> None:
        """Hand a candle on, forming or not. Only a closed one is stored; a sink takes both, and does
        the storing itself because it has to happen inside the hub's hold."""
        if self.sink is not None:
            await self.sink(candle)
        elif not candle.forming:
            await self.store(candle)

    async def store(self, candle: Candle) -> None:
        await store_closed_candle(self.pool, candle)


async def store_closed_candle(pool, candle: Candle) -> None:
    """One closed candle: stored, counted as verified, and folded into the rollups. Module-level
    because the contract layer runs it too, inside the hold that belongs to the hub."""
    period = period_length(candle.resolution)
    async with pool.acquire() as conn:
        # Verified up to the moment the period closed, not only the period itself: the period alone
        # leaves a hairline gap between candles that a coverage lookup reports as never collected.
        await commit_candles(
            conn,
            [candle],
            symbol=candle.symbol,
            resolution=candle.resolution,
            covered_from=candle.period_start,
            covered_to=max(candle.period_start + period, datetime.now(UTC)),
        )
