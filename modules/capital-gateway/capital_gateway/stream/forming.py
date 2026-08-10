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
    """Folds quotes into the current bar and takes correction from sealed ones.

    For a resolution without an arithmetic boundary the module cannot place a new period
    on its own, so it holds a second piece of state: whether the bar it has is one that
    quotes may still extend, or one whose period is over. Those were the same thing until
    it turned out they are not — see ``needs_boundary``.
    """

    def __init__(self, resolution: Resolution) -> None:
        self._step = BUCKET_SECONDS.get(resolution)
        self._bar: Bar | None = None
        # Only meaningful without a step. True means "the period this bar covers has
        # ended, and where the next one starts is not something this module may compute".
        self._closed = False

    @property
    def current(self) -> Bar | None:
        return self._bar

    @property
    def needs_boundary(self) -> bool:
        """Whether a quote cannot be folded in until the provider says where the current
        period starts.

        Two ways in, and both used to publish nothing at all. Before any sealed candle
        there is no bar — and for DAY that first seal is up to a day away, which is a
        chart standing still for a day. After one, the bar's period is over, and quotes
        belonging to the next period were being folded into it: a closed candle stretched
        by prices from a period it never covered, published as though it were forming.
        """
        return self._step is None and (self._bar is None or self._closed)

    def seed(self, bar: Bar) -> Bar:
        """The current period, as the provider reports it.

        The one legitimate source of a boundary this module refuses to compute. Unlike
        ``on_sealed`` it says the period is *running*, so quotes extend it from here.
        """
        self._bar = bar
        self._closed = False
        return bar

    def invalidate(self) -> None:
        """Forget where the current period starts, without forgetting the bar.

        Called when the feed comes back after a break: the period may have rolled over
        while nobody was watching, and the bar in hand is then the wrong one to extend.
        """
        if self._step is None:
            self._closed = True

    def on_sealed(self, bar: Bar) -> Bar:
        """A closed candle from the provider. Authoritative: it watched the whole
        period, while this module only saw it from the moment it connected.

        Without an arithmetic boundary this is also the signal that the period moved:
        the candle just sealed is finished, so the next quote belongs to a period whose
        start only the provider knows.
        """
        self._bar = bar
        if self._step is None:
            self._closed = True
        return bar

    def on_quote(self, ts_ms: int, price: float) -> Bar | None:
        """A quote. Returns the bar to publish, or None if the quote says nothing.

        The rule: floor the quote's time to its period. A quote inside the current
        period stretches the high and low and moves the close; a quote in a later period
        opens a new bar.
        """
        prev = self._bar
        if self._step is None:
            # DAY or WEEK: no arithmetic boundary to trust. Quotes extend the period the
            # provider named, and nothing else — a bar whose period has ended is left
            # alone until `seed` names the next one.
            if prev is None or self._closed:
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
