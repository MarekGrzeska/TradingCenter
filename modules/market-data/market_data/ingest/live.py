"""One pair's subscription, kept alive for as long as the operator wants it.

The loop is: close whatever gap exists, subscribe, store closed candles until the socket
ends, wait, do it again. The gap-closing is inside the loop rather than before it on
purpose — a dropped subscription is not only a socket to reopen, it is a stretch of time
nobody was listening for, and reconnecting without fetching it leaves a hole that looks
exactly like a market that was shut.

Nothing here decides whether a pair should be collected. It runs while the pair is
tracked and stops when it is not, and that decision belongs to the operator.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ..coverage import record_coverage
from ..errors import GatewayError
from ..gateway import CandleUpdate, FeedFailure, FeedState, FeedStatus, subscribe
from ..gateway import GatewayHistory as _GatewayHistory
from ..models import Resolution
from ..periods import period_length
from ..rollups import refresh_all
from ..store import write_candles
from .backfill import FillOutcome, fill_gap

log = logging.getLogger(__name__)


@dataclass
class Backoff:
    """How long to wait before trying the feed again.

    Growing, because a gateway that is down stays down for a while and a tight retry loop
    turns one outage into a second problem. Capped, because a feed that comes back after
    an hour should be picked up in a minute, not in an hour.
    """

    first: float = 1.0
    cap: float = 60.0
    factor: float = 2.0
    _current: float = field(default=0.0, init=False)

    def next_delay(self) -> float:
        self._current = self.first if self._current == 0 else min(self._current * self.factor, self.cap)
        return self._current

    def reset(self) -> None:
        """Called once a subscription actually produces something.

        On connection alone would be wrong: a gateway that accepts a socket and drops it
        immediately would reset the delay every time and retry in a hot loop.
        """
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
    limiter: object | None = None
    on_fill: Callable[[FillOutcome], None] | None = None
    # Injected so the tests can supply a feed and a clock. In the process, these are the
    # real ones.
    subscribe_to: Callable = subscribe
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    backoff: Backoff = field(default_factory=Backoff)

    async def run(self) -> None:
        """Collect this pair until it stops being tracked."""
        while await self.still_tracked():
            outcome = await self._close_gap()
            if self.on_fill is not None:
                self.on_fill(outcome)

            try:
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
        async with self.subscribe_to(self.stream_url, self.symbol, self.resolution) as messages:
            async for message in messages:
                if isinstance(message, CandleUpdate):
                    self.backoff.reset()
                    if not message.candle.forming:
                        await self._store(message.candle)
                elif isinstance(message, FeedStatus):
                    if message.state is FeedState.CONNECTED:
                        self.backoff.reset()
                elif isinstance(message, FeedFailure):
                    # The gateway reporting its own trouble. The socket is still open and
                    # the next message may well be a candle, so this is noted, not fatal.
                    log.warning(
                        "%s %s: gateway reported %s",
                        self.symbol,
                        self.resolution.value,
                        message.message,
                    )

                if not await self.still_tracked():
                    return

    async def _store(self, candle) -> None:
        """One closed candle: stored, counted as verified, and folded into the rollups."""
        period = period_length(self.resolution)
        async with self.pool.acquire() as conn:
            await write_candles(conn, [candle])
            # The period is now verified, and so is the moment it closed. Recording only
            # the period itself would leave a hairline gap between consecutive candles
            # that a coverage lookup would report as never collected.
            await record_coverage(
                conn,
                self.symbol,
                self.resolution,
                candle.period_start,
                max(candle.period_start + period, datetime.now(UTC)),
            )
            if self.resolution is Resolution.MINUTE:
                await refresh_all(conn, self.symbol, candle.period_start, candle.period_start)
