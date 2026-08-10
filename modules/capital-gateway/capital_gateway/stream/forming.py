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
    on its own, so it holds two more pieces of state beside the bar, and they are not the
    same piece. A period the provider has *sealed* is over: whatever comes next starts
    later than this bar. A boundary gone *stale* — the feed broke — may or may not still
    be the current one, and usually is. Told apart because the answer to "the provider
    handed back the same period" differs: after a seal that is no progress, after a break
    it is the confirmation being asked for.
    """

    def __init__(self, resolution: Resolution) -> None:
        self._step = BUCKET_SECONDS.get(resolution)
        self._bar: Bar | None = None
        # Both only meaningful without a step.
        self._period_over = False
        self._boundary_stale = False

    @property
    def current(self) -> Bar | None:
        return self._bar

    @property
    def needs_boundary(self) -> bool:
        """Whether a quote cannot be folded in until the provider says where the current
        period starts.

        Three ways in. Before any sealed candle there is no bar — and for DAY that first
        seal is up to a day away, which is a chart standing still for a day. After one,
        the bar's period is over, and quotes belonging to the next period were being
        folded into it: a closed candle stretched by prices from a period it never
        covered, published as though it were forming. After a break in the feed the bar
        may have stopped being current without anyone seeing it happen.
        """
        return self._step is None and (
            self._bar is None or self._period_over or self._boundary_stale
        )

    @property
    def period_is_over(self) -> bool:
        """Whether the bar in hand covers a period the provider has already sealed.

        What a caller asking the provider for the boundary needs in order to read the
        answer: the same period handed back is no progress after a seal, and exactly the
        confirmation wanted after a break in the feed.
        """
        return self._period_over

    def seed(self, bar: Bar) -> Bar:
        """The current period, as the provider reports it.

        The one legitimate source of a boundary this module refuses to compute. Unlike
        ``on_sealed`` it says the period is *running*, so quotes extend it from here.
        """
        self._bar = bar
        self._period_over = False
        self._boundary_stale = False
        return bar

    def invalidate(self) -> None:
        """Stop vouching for the bar being the current period, without declaring it over.

        Called when the feed breaks: the period may have rolled over while nobody was
        watching. Usually it has not — a drop lasting seconds inside a daily period is the
        ordinary case — so this must not be `on_sealed`'s state. Read as "over", the
        provider handing the same period back counts as no progress, the room stays silent
        and the chart stops for the rest of the day over a blip.
        """
        if self._step is None:
            self._boundary_stale = True

    def on_sealed(self, bar: Bar) -> Bar:
        """A closed candle from the provider. Authoritative: it watched the whole
        period, while this module only saw it from the moment it connected.

        Without an arithmetic boundary this is also the signal that the period moved:
        the candle just sealed is finished, so the next quote belongs to a period whose
        start only the provider knows.
        """
        self._bar = bar
        if self._step is None:
            self._period_over = True
            self._boundary_stale = False
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
            if prev is None or self._period_over or self._boundary_stale:
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
