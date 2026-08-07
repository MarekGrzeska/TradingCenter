"""The candle that has not closed yet, assembled from quotes.

This exists because of one measurement: on US100 at MINUTE_5, over sixty seconds, the
provider's candle event fired **zero** times and its quotes fired **296**. A feed
carrying only sealed candles therefore shows a chart standing still for five minutes
while the price moves — indistinguishable from a broken stream, and exactly what the
documentation says will happen.

It lives here rather than in a consumer because otherwise every consumer — a chart, an
agent, a backtest — writes its own bucketing, and three implementations of "the current
candle" disagree in the third decimal place.

No I/O, so the rules can be tested without a socket.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..dtos import Resolution

# Only intraday resolutions. Flooring a timestamp to a period is arithmetic on the
# epoch, and that is exact only while a period is a fixed number of seconds. DAY and
# WEEK boundaries follow the venue's session, not UTC midnight, so they are absent on
# purpose: a guessed daily boundary produces a candle that looks right and is wrong.
BUCKET_SECONDS: dict[Resolution, int] = {
    Resolution.MINUTE: 60,
    Resolution.MINUTE_5: 300,
    Resolution.MINUTE_15: 900,
    Resolution.MINUTE_30: 1800,
    Resolution.HOUR: 3600,
    Resolution.HOUR_4: 14400,
}


@dataclass
class Bar:
    time: int  # epoch seconds at the start of the period
    open: float
    high: float
    low: float
    close: float


class FormingCandle:
    """Folds quotes into the current bar and takes correction from sealed ones."""

    def __init__(self, resolution: Resolution) -> None:
        self._step = BUCKET_SECONDS.get(resolution)
        self._bar: Bar | None = None

    @property
    def current(self) -> Bar | None:
        return self._bar

    def seed(self, bar: Bar | None) -> None:
        """Start from the newest historical candle, so the first quote extends the
        series a consumer already has instead of opening a bar beside it."""
        self._bar = bar

    def on_sealed(self, bar: Bar) -> Bar:
        """A closed candle from the provider. Authoritative: it watched the whole
        period, while this module only saw it from the moment it connected."""
        self._bar = bar
        return bar

    def on_quote(self, ts_ms: int, price: float) -> Bar | None:
        """A quote. Returns the bar to publish, or None if the quote says nothing.

        The rule: floor the quote's time to its period. A quote inside the current
        period stretches the high and low and moves the close; a quote in a later period
        opens a new bar.
        """
        prev = self._bar
        if self._step is None:
            # DAY or WEEK: no arithmetic boundary to trust. Quotes extend the last known
            # candle and only a sealed candle from the provider moves the boundary.
            if prev is None:
                return None
            bucket = prev.time
        else:
            bucket = (ts_ms // 1000 // self._step) * self._step

        if prev is not None and bucket <= prev.time:
            self._bar = Bar(
                time=prev.time,
                open=prev.open,
                high=max(prev.high, price),
                low=min(prev.low, price),
                close=price,
            )
        else:
            self._bar = Bar(time=bucket, open=price, high=price, low=price, close=price)
        return self._bar
