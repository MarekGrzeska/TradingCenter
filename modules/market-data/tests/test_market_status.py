"""The market-status cache and the decision it feeds, tested without an HTTP client. Both used to live
inside `app.py`; the rules they encode are about traffic and staleness, not about HTTP."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from market_data.errors import GatewayUnreachable
from market_data.market_status import MarketStatus
from market_data.models import Resolution
from market_data.tracking import CollectionState, TrackedPairStatus, decide_late_pairs

NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


class FakeInstruments:
    def __init__(self, market_open: bool | None = None, error: Exception | None = None):
        self.market_open = market_open
        self.error = error
        self.asked: list[str] = []

    async def is_market_open(self, symbol: str) -> bool | None:
        self.asked.append(symbol)
        if self.error is not None:
            raise self.error
        return self.market_open


def status(
    symbol: str = "US100",
    resolution: Resolution = Resolution.MINUTE,
    collection: CollectionState = CollectionState.UNKNOWN,
    latest: datetime | None = None,
) -> TrackedPairStatus:
    return TrackedPairStatus(
        symbol=symbol,
        resolution=resolution,
        added_at=NOW - timedelta(days=1),
        collect_from=NOW - timedelta(days=1),
        earliest_candle=None,
        latest_candle=latest if latest is not None else NOW - timedelta(hours=5),
        collection=collection,
    )



async def test_a_first_reading_asks_the_gateway() -> None:
    gateway = FakeInstruments(market_open=True)

    assert await MarketStatus().of(gateway, "US100") == ("US100", True)
    assert gateway.asked == ["US100"]


async def test_a_second_reading_inside_the_window_asks_nothing() -> None:
    # The whole reason this exists: without it a shut market is permanently late, so every read of
    # the pair list spends a request per closed pair. Measured over a weekend quarter-hour: 74.
    gateway = FakeInstruments(market_open=False)
    cache = MarketStatus()

    await cache.of(gateway, "US100")
    second = await cache.of(gateway, "US100")

    assert second == ("US100", False)
    assert gateway.asked == ["US100"]


async def test_a_reading_after_the_window_asks_again() -> None:
    gateway = FakeInstruments(market_open=True)
    cache = MarketStatus(ttl=timedelta(seconds=0))

    await cache.of(gateway, "US100")
    await cache.of(gateway, "US100")

    assert gateway.asked == ["US100", "US100"]


async def test_two_instruments_are_remembered_apart() -> None:
    gateway = FakeInstruments(market_open=True)
    cache = MarketStatus()

    await cache.of(gateway, "US100")
    await cache.of(gateway, "GOLD")

    assert gateway.asked == ["US100", "GOLD"]


async def test_a_gateway_that_will_not_answer_is_remembered_too() -> None:
    """The refusal is cached like any other answer. Re-asking on every read while it is
    down spends traffic exactly when the gateway can least afford it."""
    gateway = FakeInstruments(error=GatewayUnreachable("the gateway is down"))
    cache = MarketStatus()

    assert await cache.of(gateway, "US100") == ("US100", None)
    assert await cache.of(gateway, "US100") == ("US100", None)
    assert gateway.asked == ["US100"]


async def test_two_caches_do_not_share_what_they_remember() -> None:
    """The property the module-level dict did not have, and the reason the test suite had
    to reach into `app.py` and clear it between cases."""
    gateway = FakeInstruments(market_open=True)

    await MarketStatus().of(gateway, "US100")
    await MarketStatus().of(gateway, "US100")

    assert gateway.asked == ["US100", "US100"]



async def test_a_fresh_pair_costs_the_gateway_nothing() -> None:
    """The budget rule. A pair whose newest candle is fresh reads `COLLECTING` whatever
    the market is doing, so asking about it would learn nothing that changes an answer."""
    gateway = FakeInstruments(market_open=True)
    fresh = status(collection=CollectionState.COLLECTING, latest=NOW)

    decided = await decide_late_pairs(gateway, MarketStatus(), [fresh], NOW)

    assert gateway.asked == []
    assert decided == [(fresh, CollectionState.COLLECTING)]


async def test_one_symbol_at_two_resolutions_is_one_question() -> None:
    # The same instrument has one market however many resolutions are collected from it.
    gateway = FakeInstruments(market_open=False)
    pairs = [status(resolution=Resolution.MINUTE), status(resolution=Resolution.HOUR)]

    decided = await decide_late_pairs(gateway, MarketStatus(), pairs, NOW)

    assert gateway.asked == ["US100"]
    assert [state for _, state in decided] == [CollectionState.MARKET_CLOSED] * 2


async def test_a_late_pair_with_the_market_open_is_stalled() -> None:
    gateway = FakeInstruments(market_open=True)

    [(_, state)] = await decide_late_pairs(gateway, MarketStatus(), [status()], NOW)

    assert state is CollectionState.STALLED


async def test_a_gateway_that_cannot_say_leaves_the_pair_unknown() -> None:
    """Not a failure of the read. The list is the archive's own, and not knowing why one
    pair is late is not a reason to refuse all of them."""
    gateway = FakeInstruments(error=GatewayUnreachable("the gateway is down"))

    [(_, state)] = await decide_late_pairs(gateway, MarketStatus(), [status()], NOW)

    assert state is CollectionState.UNKNOWN


@pytest.mark.parametrize("collection", [CollectionState.COLLECTING, CollectionState.NEVER_COLLECTED])
async def test_a_pair_that_already_knows_its_state_is_left_alone(
    collection: CollectionState,
) -> None:
    gateway = FakeInstruments(market_open=True)
    settled = status(collection=collection)

    decided = await decide_late_pairs(gateway, MarketStatus(), [settled], NOW)

    assert gateway.asked == []
    assert decided == [(settled, collection)]
