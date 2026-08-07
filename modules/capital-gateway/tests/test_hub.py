"""The hub against a fake upstream — the sharing and lifecycle rules, no network."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import ClassVar

from capital_gateway.dtos import Resolution
from capital_gateway.stream.hub import Hub
from capital_gateway.stream.messages import (
    CandleMessage,
    ErrorMessage,
    Message,
    QuoteMessage,
    StatusMessage,
)

BASE_MS = 1_784_988_000_000
BASE_S = BASE_MS // 1000


class FakeUpstream:
    """Stands in for the provider connection. Counts starts and stops, and lets a test
    push events as though they had arrived over the wire."""

    instances: ClassVar[list[FakeUpstream]] = []

    def __init__(self, epic: str, resolution: Resolution, emit) -> None:
        self.epic = epic
        self.resolution = resolution
        self.emit = emit
        self.started = 0
        self.stopped = 0
        FakeUpstream.instances.append(self)

    def start(self) -> None:
        self.started += 1

    async def stop(self) -> None:
        self.stopped += 1


def make_hub() -> Hub:
    FakeUpstream.instances = []
    return Hub(lambda epic, resolution, emit: FakeUpstream(epic, resolution, emit))


def collector() -> tuple[Callable[[Message], Awaitable[None]], list[Message]]:
    received: list[Message] = []

    async def subscriber(message: Message) -> None:
        received.append(message)

    return subscriber, received


async def test_a_second_subscriber_opens_no_second_connection() -> None:
    hub = make_hub()
    first, _ = collector()
    second, got_second = collector()

    await hub.subscribe("US100", Resolution.MINUTE_5, first)
    await hub.subscribe("US100", Resolution.MINUTE_5, second)

    assert len(FakeUpstream.instances) == 1
    assert FakeUpstream.instances[0].started == 1
    assert hub.room_count() == 1
    # The joiner still hears the room's state rather than waiting in silence.
    assert isinstance(got_second[0], StatusMessage)


async def test_a_different_resolution_is_a_different_room() -> None:
    hub = make_hub()
    a, _ = collector()
    b, _ = collector()

    await hub.subscribe("US100", Resolution.MINUTE_5, a)
    await hub.subscribe("US100", Resolution.HOUR, b)

    # The provider subscribes per resolution, so these cannot share a connection.
    assert len(FakeUpstream.instances) == 2


async def test_both_subscribers_receive_the_same_events() -> None:
    hub = make_hub()
    first, got_first = collector()
    second, got_second = collector()
    await hub.subscribe("US100", Resolution.MINUTE_5, first)
    await hub.subscribe("US100", Resolution.MINUTE_5, second)
    upstream = FakeUpstream.instances[0]

    await upstream.emit({"kind": "quote", "t": BASE_MS, "bid": 100.0, "ask": 100.2})

    quotes_first = [m for m in got_first if isinstance(m, QuoteMessage)]
    quotes_second = [m for m in got_second if isinstance(m, QuoteMessage)]
    assert len(quotes_first) == len(quotes_second) == 1
    assert quotes_first[0].bid == 100.0


async def test_a_quote_produces_both_a_quote_and_a_forming_candle() -> None:
    hub = make_hub()
    subscriber, received = collector()
    await hub.subscribe("US100", Resolution.MINUTE_5, subscriber)
    upstream = FakeUpstream.instances[0]

    await upstream.emit({"kind": "quote", "t": BASE_MS, "bid": 100.0, "ask": 100.2})

    candles = [m for m in received if isinstance(m, CandleMessage)]
    assert len(candles) == 1
    assert candles[0].forming is True
    # The candle is built from the bid, matching the sealed candles and REST history —
    # not from the ask and not from the midpoint.
    assert candles[0].close == 100.0


async def test_a_sealed_event_publishes_a_settled_candle() -> None:
    hub = make_hub()
    subscriber, received = collector()
    await hub.subscribe("US100", Resolution.MINUTE_5, subscriber)
    upstream = FakeUpstream.instances[0]

    await upstream.emit(
        {"kind": "sealed", "t": BASE_MS, "o": 95.0, "h": 110.0, "l": 94.0, "c": 99.0}
    )

    candle = [m for m in received if isinstance(m, CandleMessage)][-1]
    assert candle.forming is False
    assert candle.high == 110.0
    # Provider milliseconds become the seconds the message contract publishes.
    assert candle.time == BASE_S


async def test_a_late_joiner_is_handed_the_bar_already_forming() -> None:
    hub = make_hub()
    early, _ = collector()
    await hub.subscribe("US100", Resolution.MINUTE_5, early)
    upstream = FakeUpstream.instances[0]
    await upstream.emit({"kind": "quote", "t": BASE_MS, "bid": 100.0, "ask": 100.2})

    late, got_late = collector()
    await hub.subscribe("US100", Resolution.MINUTE_5, late)

    # Otherwise a tab opening on a quiet market shows nothing until the next tick.
    candles = [m for m in got_late if isinstance(m, CandleMessage)]
    assert len(candles) == 1
    assert candles[0].forming is True


async def test_the_last_leaver_closes_the_connection() -> None:
    hub = make_hub()
    first, _ = collector()
    second, _ = collector()
    await hub.subscribe("US100", Resolution.MINUTE_5, first)
    await hub.subscribe("US100", Resolution.MINUTE_5, second)
    upstream = FakeUpstream.instances[0]

    await hub.unsubscribe("US100", Resolution.MINUTE_5, first)
    assert upstream.stopped == 0  # one listener left, the feed stays up

    await hub.unsubscribe("US100", Resolution.MINUTE_5, second)

    assert upstream.stopped == 1
    assert hub.room_count() == 0


async def test_a_reconnecting_room_tells_its_subscribers() -> None:
    hub = make_hub()
    subscriber, received = collector()
    await hub.subscribe("US100", Resolution.MINUTE_5, subscriber)
    upstream = FakeUpstream.instances[0]

    await upstream.emit({"kind": "status", "state": "reconnecting"})
    await upstream.emit({"kind": "status", "state": "connected"})
    await upstream.emit({"kind": "quote", "t": BASE_MS, "bid": 100.0, "ask": 100.2})

    states = [m.state for m in received if isinstance(m, StatusMessage)]
    assert states[-2:] == ["reconnecting", "connected"]
    # And the feed resumed without the subscriber reconnecting.
    assert any(isinstance(m, QuoteMessage) for m in received)


async def test_a_subscriber_that_fails_is_dropped_not_allowed_to_silence_the_room() -> None:
    hub = make_hub()
    healthy, got_healthy = collector()

    async def broken(message: Message) -> None:
        raise RuntimeError("socket closed")

    await hub.subscribe("US100", Resolution.MINUTE_5, broken)
    await hub.subscribe("US100", Resolution.MINUTE_5, healthy)
    upstream = FakeUpstream.instances[0]

    await upstream.emit({"kind": "quote", "t": BASE_MS, "bid": 100.0, "ask": 100.2})
    await upstream.emit({"kind": "quote", "t": BASE_MS + 1000, "bid": 101.0, "ask": 101.2})

    assert len([m for m in got_healthy if isinstance(m, QuoteMessage)]) == 2


async def test_an_upstream_failure_reaches_the_subscribers() -> None:
    hub = make_hub()
    subscriber, received = collector()
    await hub.subscribe("US100", Resolution.MINUTE_5, subscriber)
    upstream = FakeUpstream.instances[0]

    await upstream.emit({"kind": "error", "message": "ERROR: error.invalid.epic"})

    # A refused subscription is silence otherwise, which a consumer reads as a quiet
    # market rather than a broken one.
    errors = [m for m in received if isinstance(m, ErrorMessage)]
    assert len(errors) == 1
    assert "error.invalid.epic" in errors[0].message


async def test_unsubscribing_from_an_unknown_room_is_not_an_error() -> None:
    hub = make_hub()
    subscriber, _ = collector()

    # A client can disconnect before its subscription completed.
    await hub.unsubscribe("US100", Resolution.MINUTE_5, subscriber)


async def test_closing_the_hub_stops_every_connection() -> None:
    hub = make_hub()
    a, _ = collector()
    b, _ = collector()
    await hub.subscribe("US100", Resolution.MINUTE_5, a)
    await hub.subscribe("GOLD", Resolution.HOUR, b)

    await hub.aclose()

    assert all(u.stopped == 1 for u in FakeUpstream.instances)
    assert hub.room_count() == 0
