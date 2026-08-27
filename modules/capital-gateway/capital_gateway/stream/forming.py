"""The candle that has not closed yet, assembled from quotes. Measured on US100 at MINUTE_5: over
sixty seconds the candle event fired zero times and quotes 296, so a sealed-only feed stands still."""

from __future__ import annotations

from dataclasses import dataclass

from ..dtos import Resolution

# Only intraday resolutions: flooring to a period is exact only while a period is a fixed number
# of seconds. DAY and WEEK follow the venue's session, and a guessed boundary looks right and is wrong.
BUCKET_SECONDS: dict[Resolution, int] = {
    Resolution.MINUTE: 60,
    Resolution.MINUTE_5: 300,
    Resolution.MINUTE_15: 900,
    Resolution.MINUTE_30: 1800,
    Resolution.HOUR: 3600,
    Resolution.HOUR_4: 14400,
}

# How long a period lasts at most, this time with DAY and WEEK. Not a boundary — it overstates
# elapsed time, which is the safe direction for "has this period certainly ended". Measured 24 Aug 2026.
NOMINAL_SECONDS: dict[Resolution, int] = {
    **BUCKET_SECONDS,
    Resolution.DAY: 86_400,
    Resolution.WEEK: 604_800,
}


@dataclass
class Bar:
    time: int  # epoch seconds at the start of the period
    open: float
    high: float
    low: float
    close: float


class FormingCandle:
    """Folds quotes into the current bar and takes correction from sealed ones. A sealed period is
    over; a stale boundary may still be current, and the two read the provider's answer differently."""

    def __init__(self, resolution: Resolution) -> None:
        self._step = BUCKET_SECONDS.get(resolution)
        self._nominal = NOMINAL_SECONDS[resolution]
        self._bar: Bar | None = None
        # Both only meaningful without a step.
        self._period_over = False
        self._boundary_stale = False
        # Whether the bar in hand is the provider's sealed candle rather than one assembled here.
        # Only a sealed one may be handed on as settled: a consumer stores what is marked settled.
        self._sealed = False

    @property
    def boundary_comes_from_provider(self) -> bool:
        """Whether this resolution's period start is something only the provider knows — what a
        caller needs to decide whether asking about a boundary is worth a timer at all."""
        return self._step is None

    @property
    def current(self) -> Bar | None:
        return self._bar

    @property
    def needs_boundary(self) -> bool:
        """Whether a quote cannot be folded in until the provider says where the period starts.
        Three ways in: no bar yet, the bar's period sealed, or a break that may have rolled it."""
        return self._step is None and (
            self._bar is None or self._period_over or self._boundary_stale
        )

    @property
    def held_is_sealed(self) -> bool:
        """Whether the bar in hand came from the provider closing the period. Not ``period_is_over``:
        a period can be known over by elapsed time while the only bar held is self-assembled."""
        return self._sealed

    @property
    def period_is_over(self) -> bool:
        """Whether the bar in hand covers a period the provider has already sealed. The same period
        handed back is no progress after a seal, and the confirmation wanted after a break."""
        return self._period_over

    def seed(self, bar: Bar) -> Bar:
        """The current period, as the provider reports it — the one legitimate source of a boundary
        this module refuses to compute. Unlike ``on_sealed`` it says the period is *running*."""
        self._bar = bar
        self._period_over = False
        self._boundary_stale = False
        self._sealed = False
        return bar

    def invalidate(self) -> None:
        """Stop vouching for the bar being current, without declaring it over. Read as "over", a
        blip in the feed would silence the room for the rest of a daily period."""
        if self._step is None:
            self._boundary_stale = True

    def on_sealed(self, bar: Bar) -> Bar:
        """A closed candle from the provider. Authoritative: it watched the whole period. Without an
        arithmetic boundary it is also the signal that the period moved."""
        self._bar = bar
        self._sealed = True
        if self._step is None:
            self._period_over = True
            self._boundary_stale = False
        return bar

    def on_quote(self, ts_ms: int, price: float) -> Bar | None:
        """A quote. Returns the bar to publish, or None if it says nothing. Floor the quote's time
        to its period: inside stretches the bar, later opens a new one."""
        prev = self._bar
        if self._step is None:
            # DAY or WEEK: no arithmetic boundary to trust. Quotes extend the period the provider
            # named, and a bar whose period ended is left alone until `seed` names the next.
            if prev is None or self._period_over or self._boundary_stale:
                return None
            if ts_ms // 1000 - prev.time >= self._nominal:
                # A whole nominal period has passed since this bar opened, so its period is over
                # whatever the venue's calendar says. The way to learn it without the seal arriving.
                self._period_over = True
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
