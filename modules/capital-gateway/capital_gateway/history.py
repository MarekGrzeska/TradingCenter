"""Reading further back than one provider request reaches.

Every constraint encoded here was measured against the live demo API, not read from
documentation:

    max per request        1000            (1001 -> error.invalid.max)
    window width           <= (max - 1) x resolution
    from/to format         YYYY-MM-DDTHH:MM:SS, UTC, no zone
    result direction       forward from `from`, not backwards from `to`
    past the oldest candle error.prices.not-found
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .dtos import Resolution

MAX_BARS_PER_REQUEST = 1000

# One period in seconds. Unlike the streaming bucket map this one includes DAY and WEEK:
# here the number only sizes a request window, and a calendar-derived width always
# *overstates* elapsed time (weekends, holidays), so it understates how many candles fit.
# Erring that way costs an extra request; erring the other way costs an error.
PERIOD_SECONDS: dict[Resolution, int] = {
    Resolution.MINUTE: 60,
    Resolution.MINUTE_5: 300,
    Resolution.MINUTE_15: 900,
    Resolution.MINUTE_30: 1800,
    Resolution.HOUR: 3600,
    Resolution.HOUR_4: 14400,
    Resolution.DAY: 86400,
    Resolution.WEEK: 604800,
}


def window_seconds(resolution: Resolution, bars: int) -> int:
    """How wide a `from`/`to` window may be for ``bars`` candles.

    The minus one is not an off-by-one guard, it is the provider's rule: the window
    counts both edges, so 1000 periods asks for 1001 candles and is refused with
    ``error.invalid.max.daterange``. Measured — 999 steps pass, 1000 do not.
    """
    return (bars - 1) * PERIOD_SECONDS[resolution]


def iso_utc(moment: datetime) -> str:
    """The provider's format: UTC, second precision, and no zone marker at all. Sending
    an offset or a trailing Z is rejected."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")


def parse_candle_ts(ts: str) -> datetime:
    """Read back what mapping wrote. The stored form carries the Z that the provider
    omits, so it round-trips through the standard parser."""
    parsed = datetime.fromisoformat(ts)
    # A candle mapped from `snapshotTime` rather than `snapshotTimeUTC` arrives naive.
    # Treating it as UTC is the same assumption the rest of the module makes.
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def page_size(bars: int) -> int:
    return min(MAX_BARS_PER_REQUEST, bars)


def window_before(anchor: datetime, resolution: Resolution, bars: int) -> tuple[str, str]:
    """The `from`/`to` pair for the page immediately older than ``anchor``."""
    return iso_utc(anchor - timedelta(seconds=window_seconds(resolution, bars))), iso_utc(anchor)
