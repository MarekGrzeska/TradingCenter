"""Facts by hand, so a strategy test says what it is about and nothing else.

Every strategy test is "given these readings, what did it decide", and the readings are the
data. Building them inline would bury one changed number under twenty unchanged ones.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta

from strategy.spec import Candle, Facts, FactValue

# A fixed instant, because a decision belongs to a bar and never to the wall clock. Tests
# that used `now()` would pass on the value of the moment they ran.
START = datetime(2026, 8, 20, 9, 0, tzinfo=UTC)


def times(count: int, *, step: timedelta = timedelta(hours=1)) -> tuple[datetime, ...]:
    return tuple(START + step * index for index in range(count))


def candles(closes: Sequence[float], *, step: timedelta = timedelta(hours=1)) -> tuple[Candle, ...]:
    """A candle per close, with a plausible body around it — enough for a strategy that
    reads closes, and honest about high/low for one that reads range."""
    stamps = times(len(closes), step=step)
    return tuple(
        Candle(
            time=stamp,
            open=close,
            high=close * 1.001,
            low=close * 0.999,
            close=close,
        )
        for stamp, close in zip(stamps, closes, strict=True)
    )


def line(key: str, name: str, values: Sequence[float | None], *, resolution: str = "HOUR") -> FactValue:
    return FactValue(
        key=key,
        resolution=resolution,
        times=times(len(values)),
        lines={name: tuple(values)},
    )


def facts(
    *,
    symbol: str = "US100",
    closes: Sequence[float] = (100.0, 101.0),
    values: Mapping[str, FactValue] | None = None,
) -> Facts:
    built = candles(closes)
    return Facts(
        symbol=symbol,
        as_of=built[-1].time,
        candles=built,
        values=dict(values or {}),
    )


def crossing_facts(
    *,
    fast: Sequence[float | None],
    slow: Sequence[float | None],
    atr: Sequence[float | None] = (1.0, 1.0),
    closes: Sequence[float] = (100.0, 101.0),
) -> Facts:
    """The baseline strategy's three readings, named the way it declares them."""
    from strategy.catalogue.baseline import FAST, RANGE, SLOW

    return facts(
        closes=closes,
        values={
            FAST: line(FAST, "ema", fast),
            SLOW: line(SLOW, "ema", slow),
            RANGE: line(RANGE, "atr", atr),
        },
    )
