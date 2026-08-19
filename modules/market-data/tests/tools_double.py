"""What the tool surface reads, doubled — the seam that used to be an HTTP client.

The tool tests moved here from a separate module, where they mocked `market-data` with
`respx` and handed back JSON. There is no request to mock now, so the double sits one
layer in: the four `reads` functions and the indicator service, which is exactly the set
a tool can reach the archive through.

Deliberately not a fake database. What these tests are about is the reduction, the
ceilings and the sentences — given an archive answer, what does the model receive. The
archive answering correctly is what `-m db` tests cover, against a real PostgreSQL.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from market_data.contract import IndicatorsOut
from market_data.models import Candle, CandleSource, CoverageRange, PriceSide, Resolution
from market_data.reads import Coverage, Forming, FormingState, Series
from market_data.tracking import CollectionState, TrackedPairStatus


def candle(
    moment: datetime,
    open_: float | None = 100.0,
    high: float | None = 101.0,
    low: float | None = 99.0,
    close: float | None = 100.0,
    resolution: Resolution = Resolution.MINUTE,
    symbol: str = "US100",
) -> Candle:
    return Candle(
        symbol=symbol,
        resolution=resolution,
        period_start=moment,
        open=open_,
        high=high,
        low=low,
        close=close,
        price_side=PriceSide.BID,
        source=CandleSource.HISTORY,
    )


def series(
    count: int,
    start: datetime | None = None,
    step: timedelta = timedelta(minutes=1),
    symbol: str = "US100",
) -> list[Candle]:
    base = start or datetime(2026, 1, 1, tzinfo=UTC)
    return [
        candle(
            base + step * i,
            open_=100 + i,
            high=101 + i,
            low=99 + i,
            close=100 + i,
            symbol=symbol,
        )
        for i in range(count)
    ]


def tracked(
    symbol: str = "US100",
    resolution: Resolution = Resolution.MINUTE,
    collection: CollectionState = CollectionState.COLLECTING,
    candle_count: int = 100,
    latest_candle: datetime | None = None,
) -> TrackedPairStatus:
    moment = datetime(2026, 1, 1, tzinfo=UTC)
    return TrackedPairStatus(
        symbol=symbol,
        resolution=resolution,
        added_at=moment,
        collect_from=moment,
        earliest_candle=moment,
        latest_candle=latest_candle,
        collection=collection,
        candle_count=candle_count,
    )


@dataclass
class FakeArchive:
    """Every answer the tools can get, set per test.

    `series_by_call` exists for the two tools that read twice — `get_last_price` falls back
    from the forming period to the newest settled candle, and `compute_indicators` reads
    closes after computing. A single `series` would make those two indistinguishable.
    """

    series: Series = field(default_factory=lambda: Series(candles=[], derived=False, uncovered=[]))
    series_by_call: list[Series] | None = None
    forming: Forming = field(
        default_factory=lambda: Forming(
            state=FormingState.NOT_TRACKED, resolution=None, candle=None, market_open=None
        )
    )
    coverage: Coverage = field(
        default_factory=lambda: Coverage(ranges=[], earliest_reachable=None)
    )
    pairs: list[TrackedPairStatus] = field(default_factory=list)
    computed: IndicatorsOut | None = None
    # For the tool that computes more than once per call: `levels_near_price` surveys the
    # catalogue in chunks of ten, and what each chunk answers depends on what it asked for.
    compute_with: Callable[[str, Any], IndicatorsOut] | None = None
    compute_error: Exception | None = None
    # A read that fails rather than answers — the archive being unreachable used to be an
    # HTTP failure and is a database one now. What it must not become is an empty answer.
    series_error: Exception | None = None

    reads: list[tuple[str, Any]] = field(default_factory=list)
    computations: list[Any] = field(default_factory=list)

    def next_series(self) -> Series:
        if self.series_by_call:
            return self.series_by_call.pop(0)
        return self.series

    def with_series(self, candles: list[Candle], **kwargs) -> FakeArchive:
        self.series = Series(
            candles=candles,
            derived=kwargs.get("derived", False),
            uncovered=kwargs.get("uncovered", []),
        )
        return self

    def with_coverage(self, ranges: list[CoverageRange], earliest=None) -> FakeArchive:
        self.coverage = Coverage(ranges=ranges, earliest_reachable=earliest)
        return self


def coverage_range(
    start: datetime,
    end: datetime,
    history_ended: bool = False,
    symbol: str = "US100",
    resolution: Resolution = Resolution.MINUTE,
) -> CoverageRange:
    return CoverageRange(
        symbol=symbol,
        resolution=resolution,
        range_start=start,
        range_end=end,
        history_ended=history_ended,
        history_ends_at=None,
    )


def forming(
    state: FormingState,
    *,
    resolution: Resolution | None = None,
    close: float | None = None,
    time: datetime | None = None,
    market_open: bool | None = None,
    symbol: str = "US100",
) -> Forming:
    """What `read_forming` answers, in the four shapes it has.

    A candle only when `close` is given: the three no-candle states are the interesting
    half of this read, and building one for them would hide which state is under test.
    """
    built = None
    if close is not None:
        built = candle(
            time or datetime.now(UTC),
            open_=close,
            high=close,
            low=close,
            close=close,
            resolution=resolution or Resolution.MINUTE,
            symbol=symbol,
        )
    return Forming(state=state, resolution=resolution, candle=built, market_open=market_open)
