"""What the archive stores, as the module sees it.

These mirror `capital-gateway`'s published vocabulary rather than importing it: modules
in this repository talk through contracts, not through each other's packages. The
spellings must match the gateway's, because they travel over its HTTP and WebSocket
contract verbatim — that is the whole coupling, and it is checked where the gateway is
read, not here.
"""

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
    """Which side of the spread a candle is built from.

    Everything stored today is `BID`, the side the gateway builds both its history and
    its stream from. The value is written next to the data anyway, so that adding the
    other side one day is a schema change with a visible cost rather than two series
    quietly averaged into one.
    """

    BID = "bid"
    ASK = "ask"


class CandleSource(str, Enum):
    """Which way a candle reached the archive.

    Kept because the two are not equally trustworthy: a stream that was disconnected
    misses quotes and understates a candle's range, while a history read sees the period
    whole. Which one wins is decided by the archive, and it cannot decide without this.
    """

    HISTORY = "history"
    STREAM = "stream"


class Candle(BaseModel):
    """One candle, identified by symbol, resolution and the start of its period.

    Edges are optional because the gateway's are: the provider occasionally omits one,
    and a candle with a missing edge is still better evidence than no candle at all.
    """

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

    # A candle the source is still building. It changes with every quote and understates
    # its own range until the period closes, so it never reaches storage — the archive
    # rejects it rather than silently dropping it, because a caller that offers one has
    # a bug worth hearing about.
    forming: bool = False

    @field_validator("period_start")
    @classmethod
    def _instant_not_a_wall_clock(cls, value: datetime) -> datetime:
        # A naive datetime is read as local time by nearly everything downstream, which
        # turns a correct candle into one an hour or two off — silently, and only for
        # some of the year. The archive's key is a moment, so it must carry a zone.
        if value.tzinfo is None:
            raise ValueError(f"period_start must carry a timezone; got the naive {value!r}")
        return value.astimezone(UTC)


class CoverageRange(BaseModel):
    """A stretch of time the archive has actually verified for one pair.

    Without this, "no candle at 3am on Saturday" and "no candle because ingest was down"
    are the same absence, and the module re-asks the provider about the same closed
    weekend forever.
    """

    symbol: str
    resolution: Resolution
    range_start: datetime
    range_end: datetime

    # True when the provider answered that it has nothing older than `history_ends_at`.
    history_ended: bool = False
    # Where it ran out — the oldest candle that read brought back, not the edge the read
    # asked about. The two are a whole window apart, and ranges merge, so reading the
    # boundary off `range_start` put it wherever the pair's oldest coverage happened to
    # begin.
    history_ends_at: datetime | None = None

    @field_validator("range_start", "range_end")
    @classmethod
    def _instant_not_a_wall_clock(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError(f"coverage bounds must carry a timezone; got the naive {value!r}")
        return value.astimezone(UTC)


class TrackedPairState(str, Enum):
    """Whether the operator currently wants this pair collected.

    An untracked pair keeps its row rather than losing it, so that tracking it again
    knows when collection stopped and can close the gap. Its candles are untouched by
    this alone — an archive MUST NOT delete data on a configuration change — but an
    operator can ask for them to be removed directly; see `deletion.py`.
    """

    TRACKED = "tracked"
    UNTRACKED = "untracked"
