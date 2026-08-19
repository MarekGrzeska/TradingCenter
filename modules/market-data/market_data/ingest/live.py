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
    gateway_api_key: str
    limiter: object | None = None
    # Where candles go instead of straight to storage. The contract layer supplies one
    # that publishes to subscribers and stores inside the same hold, so a candle can never
    # be both in a subscriber's snapshot and in the change that follows it.
    sink: Callable[[Candle], Awaitable[None]] | None = None
    # Injected so the tests can supply a feed and a clock. In the process, these are the
    # real ones.
    subscribe_to: Callable = subscribe
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    backoff: Backoff = field(default_factory=Backoff)

    async def run(self) -> None:
        """Collect this pair until it stops being tracked.

        Closing the gap is inside the guard, not before it. It reaches the database and
        the gateway, so it fails for all the reasons the feed does — and it used to fail
        *outside* any handler, which ended the loop, ended the task, and ended collection
        for this pair until somebody restarted the process. Measured on 10 August: a
        schema migration applied half an hour after the code that needed it, and every
        pair's ingest died on its first fill against the column that was not there yet.
        The archive then sat silent for forty minutes with nothing to show it, because a
        chart that has stopped and a market that has stopped look identical.
        """
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
                    # The gateway reporting its own trouble — most often its connection to
                    # the provider dropping and being remade. The socket to *us* stays
                    # open, and the next message may well be a candle, so this is not
                    # fatal and the subscription is not torn down over it.
                    #
                    # But the stretch the gateway spent disconnected is precisely a stretch
                    # nobody was listening for, and the loop above will not end, so the
                    # gap-closing at the top of `run` never comes round. Measured on
                    # 2026-08-08: a keepalive timeout upstream cost two minute candles the
                    # provider still had, coverage correctly reported them missing, and
                    # they stayed missing — because nothing was going to ask again until
                    # the module restarted.
                    #
                    # So the gap is closed here, without dropping the feed. A repeat costs
                    # nothing: with nothing missing the fill asks for zero candles.
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
        """Hand a candle on, forming or not.

        A forming candle goes no further than whoever is watching; only a closed one is
        stored. When a sink is supplied it takes both, because the thing that fans out to
        subscribers needs to see the forming ones too — and needs the store to happen
        inside its own hold, which is why it does the storing rather than this.
        """
        if self.sink is not None:
            await self.sink(candle)
        elif not candle.forming:
            await self.store(candle)

    async def store(self, candle: Candle) -> None:
        await store_closed_candle(self.pool, candle)


async def store_closed_candle(pool, candle: Candle) -> None:
    """One closed candle: stored, counted as verified, and folded into the rollups.

    A module-level function rather than a method because the contract layer runs it too —
    it has to happen inside the hold that keeps a subscriber's snapshot and the change
    that follows it from overlapping, and that hold belongs to the hub.
    """
    period = period_length(candle.resolution)
    async with pool.acquire() as conn:
        # Verified up to the moment the period closed, not only the period itself —
        # recording the period alone would leave a hairline gap between consecutive
        # candles that a coverage lookup would report as never collected.
        await commit_candles(
            conn,
            [candle],
            symbol=candle.symbol,
            resolution=candle.resolution,
            covered_from=candle.period_start,
            covered_to=max(candle.period_start + period, datetime.now(UTC)),
        )
