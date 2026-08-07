"""Reaching back for what the archive does not have.

Two rules shape this. The gateway pages past the provider's thousand-candle ceiling and
owns the rate gate, so there is no paging here — one request per fill, however deep. And
a deep fill is dozens of provider calls behind that one request, so fills run under a
budget: two of them together are enough to starve the chart an operator is looking at
right now, and that operator's reads go through the same ten-requests-a-second gate.

The other half of the job is knowing when *not* to ask. An archive that refetches the
same closed weekend every night is worse than one that is merely behind, because it
spends the budget that would have closed a real gap.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from pydantic import BaseModel

from ..coverage import record_coverage
from ..errors import GatewayError
from ..gateway import GatewayHistory
from ..models import Resolution
from ..periods import period_length
from ..rollups import refresh_all
from ..store import read_latest_period, write_candles

log = logging.getLogger(__name__)

# The gateway's own ceiling on a single history request. Asking for more is refused with a
# validation error rather than being clamped, so it is clamped here.
MAX_BARS_PER_FILL = 50_000

# A little overlap on every fill, so the seam between what the archive holds and what it
# is fetching is covered twice rather than nearly. Refetching a period costs nothing —
# the store overwrites it, and a history value is the one that should win anyway.
OVERLAP_BARS = 2


class FillOutcome(BaseModel):
    """What one fill did, in terms an operator can act on.

    Both halves matter. `written` says whether the archive actually gained anything, and
    `requests` says what it cost upstream — a fill that took thirty provider calls to
    write four candles is working correctly and still worth seeing.
    """

    symbol: str
    resolution: Resolution
    # What was asked of the gateway. Zero means no request was made at all, which is the
    # right outcome for a pair that is already current.
    requested: int
    written: int = 0
    # Provider calls the gateway made behind the one request, as it reported them.
    requests: int = 0
    history_ended: bool = False
    covered_from: datetime | None = None
    covered_to: datetime | None = None
    # Present when the fill failed. Named, never a raw database error or a credential.
    failure: str | None = None
    finished_at: datetime | None = None

    @property
    def asked_the_provider(self) -> bool:
        return self.requested > 0

    def describe(self) -> str:
        """One line, for a log an operator reads at three in the morning."""
        pair = f"{self.symbol} {self.resolution.value}"
        if self.failure:
            return f"{pair}: fill failed — {self.failure}"
        if not self.asked_the_provider:
            return f"{pair}: already current, nothing requested"
        ended = ", provider history ended" if self.history_ended else ""
        return (
            f"{pair}: asked for {self.requested} candles, wrote {self.written} "
            f"in {self.requests} provider request(s){ended}"
        )


def bars_to_close_gap(
    resolution: Resolution,
    latest_candle: datetime | None,
    now: datetime,
    default_bars: int,
) -> int:
    """How many candles to ask for, or zero when the archive is already current.

    A pair that has collected nothing reaches back `default_bars`. A pair that has been
    collecting asks only for what it missed.

    Zero is the important answer. At any moment the newest closed candle is up to one
    period old — the current period has not finished, so the provider does not have it
    either — and treating that as a gap would send a request every period, forever, for
    a candle nobody has yet.
    """
    if latest_candle is None:
        return min(default_bars, MAX_BARS_PER_FILL)

    period = period_length(resolution)
    behind = now - latest_candle
    missing = int(behind / period) - 1
    if missing <= 0:
        return 0
    return min(missing + OVERLAP_BARS, MAX_BARS_PER_FILL)


async def fill_gap(
    pool,
    history: GatewayHistory,
    symbol: str,
    resolution: Resolution,
    *,
    default_bars: int,
    limiter=None,
    now: datetime | None = None,
) -> FillOutcome:
    """Close whatever gap this pair has, and record what was verified.

    `limiter` is the budget — an `asyncio.Semaphore` shared by every fill in the process.
    It is taken only around the provider call, so reading the archive to work out whether
    a call is needed at all never waits behind another pair's deep fill.
    """
    moment = now or datetime.now(UTC)

    async with pool.acquire() as conn:
        latest = await read_latest_period(conn, symbol, resolution)

    bars = bars_to_close_gap(resolution, latest, moment, default_bars)
    if bars == 0:
        outcome = FillOutcome(
            symbol=symbol, resolution=resolution, requested=0, finished_at=moment
        )
        log.info(outcome.describe())
        return outcome

    try:
        if limiter is not None:
            async with limiter:
                page = await history.history(symbol, resolution, bars)
        else:
            page = await history.history(symbol, resolution, bars)
    except GatewayError as err:
        # Named rather than raised on. A pair whose fill failed is not a reason to stop
        # collecting the others, and the reason has to survive to somewhere an operator
        # reads.
        outcome = FillOutcome(
            symbol=symbol,
            resolution=resolution,
            requested=bars,
            failure=str(err),
            finished_at=datetime.now(UTC),
        )
        log.warning(outcome.describe())
        return outcome

    written = 0
    covered_from = covered_to = None
    if page.candles:
        oldest = page.candles[0].period_start
        newest = page.candles[-1].period_start
        async with pool.acquire() as conn:
            written = await write_candles(conn, page.candles)
            # Verified up to the moment of the read, not up to the newest candle. The two
            # differ exactly when the market was shut for the tail of the window — and
            # recording only as far as the last candle is what would send this same
            # request again tomorrow, and every day after.
            covered = await record_coverage(
                conn,
                symbol,
                resolution,
                oldest,
                max(newest + period_length(resolution), moment),
                history_ended=page.history_ended,
            )
            covered_from, covered_to = covered.range_start, covered.range_end
            if resolution is Resolution.MINUTE:
                await refresh_all(conn, symbol, oldest, newest)

    outcome = FillOutcome(
        symbol=symbol,
        resolution=resolution,
        requested=bars,
        written=written,
        requests=page.requests,
        history_ended=page.history_ended,
        covered_from=covered_from,
        covered_to=covered_to,
        finished_at=datetime.now(UTC),
    )
    log.info(outcome.describe())
    return outcome
