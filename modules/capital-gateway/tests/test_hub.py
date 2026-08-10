"""The hub against a fake upstream — the sharing and lifecycle rules, no network."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import ClassVar

from capital_gateway.dtos import Resolution
from capital_gateway.stream.forming import Bar
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


async def test_a_streamed_candle_carries_no_volume() -> None:
    hub = make_hub()
    subscriber, received = collector()
    await hub.subscribe("US100", Resolution.MINUTE_5, subscriber)
    upstream = FakeUpstream.instances[0]

    await upstream.emit({"kind": "quote", "t": BASE_MS, "bid": 100.0, "ask": 100.2})
    await upstream.emit(
        {"kind": "sealed", "t": BASE_MS, "o": 95.0, "h": 110.0, "l": 94.0, "c": 99.0}
    )

    # Neither provider event carries volume, so the field is null on this feed — forming
    # and sealed alike. It exists so the shape matches the REST candle; pinning it here
    # means a consumer reading a zero one day is a change somebody made, not a surprise.
    candles = [m for m in received if isinstance(m, CandleMessage)]
    assert len(candles) == 2
    assert all(c.volume is None for c in candles)


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


# --- the boundary a session-bound resolution cannot compute ---


def make_seeded_hub(
    bars: list[Bar | None],
) -> tuple[Hub, list[tuple[str, Resolution]]]:
    """A hub whose rooms can ask where the current period starts, answering from `bars`
    in order and repeating the last answer once it runs out."""
    asked: list[tuple[str, Resolution]] = []
    FakeUpstream.instances = []

    async def current_period(epic: str, resolution: Resolution) -> Bar | None:
        asked.append((epic, resolution))
        return bars[min(len(asked) - 1, len(bars) - 1)]

    hub = Hub(
        lambda epic, resolution, emit: FakeUpstream(epic, resolution, emit), current_period
    )
    return hub, asked


async def test_a_daily_room_publishes_before_the_provider_seals_anything() -> None:
    """The defect in one test: a daily candle is sealed once a day, so a room that waited
    for one published nothing for up to that long."""
    hub, asked = make_seeded_hub([Bar(time=BASE_S, open=100.0, high=100.0, low=100.0, close=100.0)])
    subscriber, received = collector()

    await hub.subscribe("US100", Resolution.DAY, subscriber)
    await FakeUpstream.instances[0].emit(
        {"kind": "quote", "t": BASE_MS + 3_600_000, "bid": 120.0, "ask": 120.2}
    )

    candles = [m for m in received if isinstance(m, CandleMessage)]
    assert candles, "no forming candle, and no sealed candle is coming for hours"
    assert candles[-1].forming is True
    assert candles[-1].time == BASE_S
    assert candles[-1].high == 120.0
    assert asked == [("US100", Resolution.DAY)]


async def test_a_daily_room_asks_again_once_the_provider_seals_the_period() -> None:
    first = Bar(time=BASE_S, open=100.0, high=100.0, low=100.0, close=100.0)
    second = Bar(
        time=BASE_S + 86_400, open=104.0, high=104.0, low=104.0, close=104.0
    )
    hub, asked = make_seeded_hub([first, second])
    subscriber, received = collector()

    await hub.subscribe("US100", Resolution.DAY, subscriber)
    upstream = FakeUpstream.instances[0]
    await upstream.emit(
        {
            "kind": "sealed",
            "t": BASE_S * 1000,
            "o": 100.0,
            "h": 105.0,
            "l": 99.0,
            "c": 104.0,
        }
    )
    await upstream.emit(
        {"kind": "quote", "t": (BASE_S + 86_400 + 60) * 1000, "bid": 120.0, "ask": 120.2}
    )

    assert len(asked) == 2, "the seal moved the boundary and nobody but the provider knows where"
    candles = [m for m in received if isinstance(m, CandleMessage)]
    settled = [c for c in candles if not c.forming]
    assert settled[-1].time == BASE_S
    assert settled[-1].high == 105.0, "the sealed candle kept its own range"
    assert candles[-1].forming is True
    assert candles[-1].time == BASE_S + 86_400, "the new period, not the one that closed"


async def test_a_provider_with_no_newer_period_leaves_the_room_silent() -> None:
    """The degradation, and it is the honest one: a bar placed by arithmetic here is the
    candle this change exists to stop publishing."""
    hub, _ = make_seeded_hub([None])
    subscriber, received = collector()

    await hub.subscribe("US100", Resolution.DAY, subscriber)
    await FakeUpstream.instances[0].emit(
        {"kind": "quote", "t": BASE_MS, "bid": 120.0, "ask": 120.2}
    )

    assert not [m for m in received if isinstance(m, CandleMessage)]
    # The price still moves; only the candle is withheld.
    assert [m for m in received if isinstance(m, QuoteMessage)]


async def test_a_boundary_read_that_raises_does_not_take_the_feed_with_it() -> None:
    FakeUpstream.instances = []

    async def current_period(epic: str, resolution: Resolution) -> Bar | None:
        raise RuntimeError("provider said no")

    hub = Hub(
        lambda epic, resolution, emit: FakeUpstream(epic, resolution, emit), current_period
    )
    subscriber, received = collector()

    await hub.subscribe("US100", Resolution.DAY, subscriber)
    await FakeUpstream.instances[0].emit(
        {"kind": "quote", "t": BASE_MS, "bid": 120.0, "ask": 120.2}
    )

    assert [m for m in received if isinstance(m, QuoteMessage)]
    assert not [m for m in received if isinstance(m, CandleMessage)]


async def test_a_fixed_period_room_never_asks_about_a_boundary() -> None:
    hub, asked = make_seeded_hub([Bar(time=BASE_S, open=1.0, high=1.0, low=1.0, close=1.0)])
    subscriber, received = collector()

    await hub.subscribe("US100", Resolution.MINUTE_5, subscriber)
    await FakeUpstream.instances[0].emit(
        {"kind": "quote", "t": BASE_MS, "bid": 120.0, "ask": 120.2}
    )

    assert asked == []
    candles = [m for m in received if isinstance(m, CandleMessage)]
    assert candles[-1].forming is True


async def test_a_provider_that_keeps_saying_no_is_not_asked_once_per_quote() -> None:
    """A liquid instrument quotes hundreds of times a minute, and every one of those
    would otherwise become a request through the same rate gate an operator's chart reads
    through."""
    hub, asked = make_seeded_hub([None])
    subscriber, _ = collector()

    await hub.subscribe("US100", Resolution.DAY, subscriber)
    upstream = FakeUpstream.instances[0]
    for n in range(20):
        await upstream.emit(
            {"kind": "quote", "t": BASE_MS + n * 1_000, "bid": 120.0, "ask": 120.2}
        )

    assert len(asked) == 1


async def test_a_reconnect_re_reads_the_boundary_it_may_have_missed() -> None:
    """The period can roll over while the feed is down, so the bar in hand is no longer
    known to be the one quotes belong to."""
    first = Bar(time=BASE_S, open=100.0, high=100.0, low=100.0, close=100.0)
    second = Bar(time=BASE_S + 86_400, open=104.0, high=104.0, low=104.0, close=104.0)
    hub, asked = make_seeded_hub([first, second])
    subscriber, received = collector()

    await hub.subscribe("US100", Resolution.DAY, subscriber)
    upstream = FakeUpstream.instances[0]
    await upstream.emit({"kind": "status", "state": "reconnecting"})
    await upstream.emit(
        {"kind": "quote", "t": (BASE_S + 86_400 + 60) * 1000, "bid": 130.0, "ask": 130.2}
    )

    assert len(asked) == 2
    candles = [m for m in received if isinstance(m, CandleMessage)]
    assert candles[-1].time == BASE_S + 86_400
