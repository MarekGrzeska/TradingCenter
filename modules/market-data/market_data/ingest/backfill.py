"""Reaching back for what the archive does not have. One request per fill, however deep, under a
budget — and the other half of the job is knowing when *not* to ask."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from pydantic import BaseModel

from ..errors import GatewayError
from ..gateway import GatewayHistory
from ..models import Resolution
from ..periods import period_length, periods_between
from ..store import commit_candles, read_latest_period
from ..tracking import read_collect_from

log = logging.getLogger(__name__)

# The gateway's own ceiling on a single history request. Asking for more is refused with a
# validation error rather than being clamped, so it is clamped here.
MAX_BARS_PER_FILL = 50_000

# A little overlap on every fill, so the seam between what the archive holds and what it fetches is
# covered twice rather than nearly. Refetching costs nothing: a history value should win anyway.
OVERLAP_BARS = 2


class FillOutcome(BaseModel):
    """What one fill did, in terms an operator can act on. `written` says whether the archive gained
    anything and `requests` what it cost upstream — thirty calls for four candles is worth seeing."""

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
    collect_from: datetime,
) -> int:
    """How many candles to ask for, or zero when the archive is already current. Zero is the important
    answer: the newest closed candle is up to one period old, and treating that as a gap never ends."""
    if latest_candle is None:
        return min(default_bars, MAX_BARS_PER_FILL, periods_between(resolution, collect_from, now))

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
    """Close whatever gap this pair has, and record what was verified. `limiter` is taken only around
    the provider call, so reading the archive never waits behind another pair's deep fill."""
    moment = now or datetime.now(UTC)

    async with pool.acquire() as conn:
        latest = await read_latest_period(conn, symbol, resolution)
        collect_from = await read_collect_from(conn, symbol, resolution)

    if collect_from is None:
        # Untracked between `PairIngest.run()`'s own check and this read — nothing to fetch for a
        # pair nobody collects, and never a fall-back to the old unclamped depth.
        outcome = FillOutcome(symbol=symbol, resolution=resolution, requested=0, finished_at=moment)
        log.info(outcome.describe())
        return outcome

    bars = bars_to_close_gap(resolution, latest, moment, default_bars, collect_from)
    if bars == 0:
        outcome = FillOutcome(
            symbol=symbol, resolution=resolution, requested=0, finished_at=moment
        )
        log.info(outcome.describe())
        return outcome

    try:
        if limiter is not None:
            async with limiter:
                page = await history.history(symbol, resolution, bars, after=collect_from)
        else:
            page = await history.history(symbol, resolution, bars, after=collect_from)
    except GatewayError as err:
        # Named rather than raised on: one pair's failed fill is not a reason to stop collecting
        # the others, and the reason has to survive to somewhere an operator reads.
        outcome = FillOutcome(
            symbol=symbol,
            resolution=resolution,
            requested=bars,
            failure=str(err),
            finished_at=datetime.now(UTC),
        )
        log.warning(outcome.describe())
        return outcome

    # Nothing older than this pair was asked to reach back to, whatever came back: a promise about
    # what the archive stores is not one to delegate. And nothing forming, or the gap looks closed.
    within = [c for c in page.candles if c.period_start >= collect_from and not c.forming]

    written = 0
    covered_from = covered_to = None
    if within:
        oldest = within[0].period_start
        newest = within[-1].period_start
        async with pool.acquire() as conn:
            committed = await commit_candles(
                conn,
                within,
                symbol=symbol,
                resolution=resolution,
                covered_from=oldest,
                # Verified up to the moment of the read, not the newest candle. The two differ when
                # the market was shut for the tail, and the shorter one re-sends this request daily.
                covered_to=max(newest + period_length(resolution), moment),
                history_ended=page.history_ended,
                # Where the read ran out, which for a fill is the oldest candle it came back with —
                # never the moment it was clipped to, which says nothing about the provider.
                history_ends_at=oldest if page.history_ended else None,
            )
            written = committed.written
            covered_from = committed.coverage.range_start
            covered_to = committed.coverage.range_end

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
