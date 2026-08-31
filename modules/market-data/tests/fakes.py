"""The doubles every suite over the app shares, and the clock they agree on. Here rather than in
`conftest.py` because these are imported by name, not injected."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from market_data.models import Candle, CandleSource, Resolution

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
LIMIT = 20

# Every read of a range says which range: `/candles` defaults to the last day of the real clock, so
# omitting the window asserts nothing once the wall clock drifts a day from `NOW`. Two tests did.
WINDOW = {
    "from": (NOW - timedelta(hours=1)).isoformat(),
    "to": (NOW + timedelta(minutes=1)).isoformat(),
}


def candle(offset: int = 0, **overrides) -> Candle:
    return Candle(
        **{
            "symbol": "US100",
            "resolution": Resolution.MINUTE,
            "period_start": NOW - timedelta(minutes=offset),
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 10.0,
            "source": CandleSource.HISTORY,
            **overrides,
        }
    )


class FakeInstruments:
    def __init__(
        self,
        collectable: bool = True,
        error: Exception | None = None,
        market_open: bool | None = None,
        search_results: list[dict] | None = None,
    ):
        self.collectable = collectable
        self.error = error
        self.search_results = search_results
        # What the gateway would say about the instrument's session. `None` is the
        # default because it is the honest one for a fake: no answer, so `UNKNOWN`.
        self.market_open = market_open
        self.asked: list[str] = []

    async def is_collectable(self, symbol: str, resolution: Resolution) -> bool:
        if self.error is not None:
            raise self.error
        return self.collectable

    async def is_market_open(self, symbol: str) -> bool | None:
        self.asked.append(symbol)
        if self.error is not None:
            raise self.error
        return self.market_open

    async def catalogue(self, max_nodes: int | None, asset_class: str | None) -> dict:
        if self.error is not None:
            raise self.error
        return {
            "instruments": [],
            "count": 0,
            "truncated": False,
            "max_nodes": max_nodes,
            "asset_class": asset_class,
        }

    async def search(self, q: str) -> list:
        if self.error is not None:
            raise self.error
        # One hit derived from the query unless a test says otherwise. `search_results` exists for
        # the tool surface, whose whole question is what it does with more matches than it shows.
        if self.search_results is not None:
            return self.search_results
        return [{"symbol": q.upper(), "name": q, "asset_class": "CRYPTO", "tradeable": True}]

    async def asset_classes(self) -> list:
        if self.error is not None:
            raise self.error
        return ["CRYPTO", "SHARES"]


class FakeInstrumentsBySymbol:
    """Like `FakeInstruments`, but collectability varies per symbol — for a multi-pair
    request where one symbol is refused and the others are not."""

    def __init__(self, collectable: dict[str, bool]) -> None:
        self._collectable = collectable

    async def is_collectable(self, symbol: str, resolution: Resolution) -> bool:
        return self._collectable.get(symbol, False)

    async def is_market_open(self, symbol: str) -> bool | None:
        return None


class FakeIngest:
    """Stands in for the supervisor: reconciles, and says what it is running."""

    def __init__(self) -> None:
        self.syncs = 0
        self.running: set = set()
        self.started_at = NOW

    async def sync(self) -> None:
        self.syncs += 1


class FakeJobRunner:
    """Stands in for the runner: real chunks still get worked, but by whatever executes
    them directly in a test — `notify()` here is just observed, never acted on."""

    def __init__(self) -> None:
        self.notifications = 0

    def notify(self) -> None:
        self.notifications += 1


def at(stamp: str) -> datetime:
    """The instant a timestamp names, however it was spelled. Comparing strings would test pydantic's
    choice of suffix rather than whether the archive answered with the right moment."""
    return datetime.fromisoformat(stamp)
