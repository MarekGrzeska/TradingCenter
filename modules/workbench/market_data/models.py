"""What the archive stores, as the module sees it. These mirror `capital-gateway`'s published
vocabulary rather than importing it: modules here talk through contracts, not each other's packages."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, field_validator


class Resolution(str, Enum):
    """Candle time frame — the gateway's vocabulary, spelled its way."""

    MINUTE = "MINUTE"
    MINUTE_5 = "MINUTE_5"
    MINUTE_15 = "MINUTE_15"
    MINUTE_30 = "MINUTE_30"
    HOUR = "HOUR"
    HOUR_4 = "HOUR_4"
    DAY = "DAY"
    WEEK = "WEEK"


class PriceSide(str, Enum):
    """Which side of the spread a candle is built from. Everything stored today is `BID`; the value is
    written next to the data so adding the other side is a schema change with a visible cost."""

    BID = "bid"
    ASK = "ask"


class CandleSource(str, Enum):
    """Which way a candle reached the archive. The two are not equally trustworthy: a disconnected
    stream understates a candle's range, while a history read sees the period whole."""

    HISTORY = "history"
    STREAM = "stream"


class Candle(BaseModel):
    """One candle, identified by symbol, resolution and the start of its period. Edges are optional
    because the gateway's are, and a candle with a missing edge beats no candle at all."""

    symbol: str
    resolution: Resolution
    period_start: datetime
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    price_side: PriceSide = PriceSide.BID
    source: CandleSource

    # A candle the source is still building. It never reaches storage, and the archive rejects it
    # rather than dropping it silently: a caller that offers one has a bug worth hearing about.
    forming: bool = False

    @field_validator("period_start")
    @classmethod
    def _instant_not_a_wall_clock(cls, value: datetime) -> datetime:
        # A naive datetime is read as local time by nearly everything downstream, which turns a
        # correct candle into one an hour off — silently, and only for some of the year.
        if value.tzinfo is None:
            raise ValueError(f"period_start must carry a timezone; got the naive {value!r}")
        return value.astimezone(UTC)


class CoverageRange(BaseModel):
    """A stretch of time the archive has actually verified for one pair. Without it, "no candle on
    Saturday" and "no candle because ingest was down" are the same absence."""

    symbol: str
    resolution: Resolution
    range_start: datetime
    range_end: datetime

    # True when the provider answered that it has nothing older than `history_ends_at`.
    history_ended: bool = False
    # Where it ran out — the oldest candle that read brought back, not the edge it asked about. The
    # two are a whole window apart, and ranges merge, so `range_start` slides.
    history_ends_at: datetime | None = None

    @field_validator("range_start", "range_end")
    @classmethod
    def _instant_not_a_wall_clock(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError(f"coverage bounds must carry a timezone; got the naive {value!r}")
        return value.astimezone(UTC)


# A rough, deliberately round figure for one stored candle: eight numeric columns plus per-row
# overhead. Here, not next to one reader, because a job's price and a pair's size must agree.
ESTIMATED_BYTES_PER_CANDLE = 96


class TrackedPairState(str, Enum):
    """Whether the operator currently wants this pair collected. An untracked pair keeps its row, so
    tracking it again knows when collection stopped; removing its candles is `deletion.py`."""

    TRACKED = "tracked"
    UNTRACKED = "untracked"
