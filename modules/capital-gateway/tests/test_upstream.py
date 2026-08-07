"""What the provider says, and what leaves the module as a result.

The translation is tested without a socket: `_on_message` is fed the frames capital.com
sends and the emitted events are collected.

The connection loop is tested against a scripted socket, which proves only what a scripted
socket can prove: that `_run` connects, subscribes, reports state, and comes back after a
drop instead of dying quietly. That the provider accepts those frames is a separate claim,
and it belongs to the live smoke tests — a fake would happily accept a subscription
capital.com refuses.
"""

from __future__ import annotations

import asyncio
import json
from collections import deque
from collections.abc import Callable
from typing import Self

import pytest
from websockets.exceptions import ConnectionClosedError

from capital_gateway.dtos import Resolution
from capital_gateway.stream import upstream as upstream_module
from capital_gateway.stream.upstream import Tokens, Upstream

EPIC = "US100"


def make_upstream() -> tuple[Upstream, list[dict]]:
    emitted: list[dict] = []

    async def emit(event: dict) -> None:
        emitted.append(event)

    async def tokens() -> tuple[str, str]:
        return ("cst-value", "token-value")

    return (
        Upstream("wss://example.invalid/connect", EPIC, Resolution.MINUTE_5, tokens, emit),
        emitted,
    )


def ohlc(price_type: str, epic: str = EPIC) -> str:
    return json.dumps(
        {
            "destination": "ohlc.event",
            "payload": {
                "epic": epic,
                "priceType": price_type,
                "t": 1_784_988_000_000,
                "o": 100.0,
                "h": 110.0,
                "l": 95.0,
                "c": 105.0,
            },
        }
    )


async def test_a_sealed_candle_is_published_once_per_period() -> None:
    up, emitted = make_upstream()

    await up._on_message(ohlc("bid"))
    await up._on_message(ohlc("ask"))

    # The provider sends the same candle twice, once per price side. Publishing both is
    # what makes a chart jump the spread — about 1.8 points on US100.
    sealed = [e for e in emitted if e["kind"] == "sealed"]
    assert len(sealed) == 1
    assert sealed[0]["o"] == 100.0


async def test_the_kept_side_is_the_one_history_uses() -> None:
    up, emitted = make_upstream()

    await up._on_message(ohlc("ask"))

    # Bid, matching mapping.candle_from_price — so history and live data join without a
    # step. Keeping ask here would be invisible until the seam was plotted.
    assert emitted == []
    assert upstream_module._KEPT_PRICE_TYPE == "bid"


async def test_a_quote_is_translated_not_forwarded() -> None:
    up, emitted = make_upstream()

    await up._on_message(
        json.dumps(
            {
                "destination": "quote",
                "payload": {
                    "epic": EPIC,
                    "timestamp": 1_784_988_001_234,
                    "bid": 100.1,
                    "ofr": 100.3,
                    "somethingElseEntirely": "provider detail",
                },
            }
        )
    )

    # `ofr` becomes `ask`, and nothing else from the provider's frame survives.
    assert emitted == [{"kind": "quote", "t": 1_784_988_001_234, "bid": 100.1, "ask": 100.3}]


async def test_another_instrument_on_the_same_socket_is_ignored() -> None:
    up, emitted = make_upstream()

    await up._on_message(ohlc("bid", epic="GOLD"))

    assert emitted == []


async def test_a_failed_subscription_is_reported_rather_than_silent() -> None:
    up, emitted = make_upstream()

    await up._on_message(
        json.dumps({"status": "ERROR", "payload": {"errorCode": "error.invalid.epic"}})
    )

    # Without this a refused subscription is indistinguishable from a quiet market.
    assert emitted[0]["kind"] == "error"
    assert "error.invalid.epic" in emitted[0]["message"]


async def test_an_ok_status_frame_is_not_an_error() -> None:
    up, emitted = make_upstream()

    await up._on_message(json.dumps({"status": "OK", "payload": {}}))

    assert emitted == []


async def test_a_frame_that_is_not_json_is_dropped() -> None:
    up, emitted = make_upstream()

    await up._on_message("<html>gateway timeout</html>")

    # A proxy erroring mid-stream should not take the reader loop down with it.
    assert emitted == []


async def test_credentials_never_appear_in_an_emitted_event() -> None:
    up, emitted = make_upstream()

    await up._on_message(ohlc("bid"))
    await up._on_message(
        json.dumps(
            {
                "destination": "quote",
                "payload": {"epic": EPIC, "timestamp": 1, "bid": 1.0, "ofr": 1.1},
            }
        )
    )
    await up._on_message(json.dumps({"status": "ERROR", "payload": {"cst": "cst-value"}}))

    blob = json.dumps(emitted)
    assert "cst-value" not in blob
    assert "token-value" not in blob


class FakeSocket:
    """Collects what would go over the wire."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send(self, raw: str) -> None:
        self.sent.append(json.loads(raw))


async def test_both_subscriptions_carry_the_tokens_in_the_message() -> None:
    up, _ = make_upstream()
    ws = FakeSocket()

    await up._subscribe(ws, "cst-value", "token-value")

    destinations = [m["destination"] for m in ws.sent]
    # Neither is sufficient alone: the candle event fires only on close, the quote feed
    # carries no candle at all.
    assert destinations == ["OHLCMarketData.subscribe", "marketData.subscribe"]
    for message in ws.sent:
        # In the body, not in a header — which is why this cannot be a reverse proxy.
        assert message["cst"] == "cst-value"
        assert message["securityToken"] == "token-value"
    assert ws.sent[0]["payload"]["resolutions"] == ["MINUTE_5"]
    assert ws.sent[0]["payload"]["type"] == "classic"


async def test_an_idle_connection_is_kept_alive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(upstream_module, "PING_INTERVAL_SECONDS", 0.01)
    up, _ = make_upstream()
    ws = FakeSocket()

    task = asyncio.create_task(up._ping_forever(ws, "cst-value", "token-value"))
    await asyncio.sleep(0.05)
    task.cancel()

    # The provider drops a connection that says nothing for ten minutes, and a dropped
    # feed looks exactly like a flat market.
    assert ws.sent
    assert all(m["destination"] == "ping" for m in ws.sent)
    assert ws.sent[0]["cst"] == "cst-value"


def test_the_ping_interval_leaves_room_under_the_provider_limit() -> None:
    # The documented tolerance is ten minutes. A margin costs one small frame; missing
    # it costs the feed.
    assert upstream_module.PING_INTERVAL_SECONDS <= 5 * 60


# --- the connection loop ---------------------------------------------------------------
#
# `_run` and `_session` are the reconnection policy. What follows drives them against a
# scripted socket, so the claim is narrow on purpose: the loop reconnects, resubscribes
# and reports what happened. Whether capital.com accepts those frames is the live suite's
# claim, not this one.


class ScriptedSocket:
    """A socket that hands over scripted frames and then ends the way the script says.

    ``ending="drop"`` raises what a real disconnect raises out of ``async for``;
    ``ending="hang"`` stays open and silent, which is what a healthy idle feed looks like
    and what keeps the loop parked instead of spinning.
    """

    def __init__(self, frames: list[str] | None = None, ending: str = "hang") -> None:
        self._frames = deque(frames or [])
        self._ending = ending
        self.sent: list[dict] = []

    async def send(self, raw: str) -> None:
        self.sent.append(json.loads(raw))

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> bool:
        return False

    def __aiter__(self) -> ScriptedSocket:
        return self

    async def __anext__(self) -> str:
        if self._frames:
            return self._frames.popleft()
        if self._ending == "drop":
            raise ConnectionClosedError(None, None)
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


class Provider:
    """Stands in for ``websockets.connect``, handing out sockets in order.

    Runs out into silent sockets rather than raising, so a test asserting on the second
    connection is not also asserting on how many the loop makes after that.
    """

    def __init__(self, sockets: list[ScriptedSocket]) -> None:
        self._queue = deque(sockets)
        self.urls: list[str] = []
        self.opened: list[ScriptedSocket] = []

    def connect(self, url: str) -> ScriptedSocket:
        self.urls.append(url)
        socket = self._queue.popleft() if self._queue else ScriptedSocket()
        self.opened.append(socket)
        return socket


URL = "wss://example.invalid/connect"


def run_upstream(
    monkeypatch: pytest.MonkeyPatch,
    sockets: list[ScriptedSocket],
    tokens: Tokens | None = None,
) -> tuple[Upstream, list[dict], Provider]:
    """An `Upstream` wired to scripted sockets, not started yet."""
    monkeypatch.setattr(upstream_module, "RECONNECT_DELAY_SECONDS", 0.0)
    provider = Provider(sockets)
    monkeypatch.setattr(upstream_module.websockets, "connect", provider.connect)

    emitted: list[dict] = []

    async def emit(event: dict) -> None:
        emitted.append(event)

    async def default_tokens() -> tuple[str, str]:
        return ("cst-value", "token-value")

    up = Upstream(URL, EPIC, Resolution.MINUTE_5, tokens or default_tokens, emit)
    return up, emitted, provider


async def until(predicate: Callable[[], bool], timeout: float = 2.0) -> None:
    """Let the loop run until it has done the thing, or fail the test saying it did not."""

    async def poll() -> None:
        while not predicate():
            await asyncio.sleep(0.005)

    try:
        await asyncio.wait_for(poll(), timeout)
    except TimeoutError:
        raise AssertionError(f"condition not reached within {timeout}s") from None


QUOTE_FRAME = json.dumps(
    {
        "destination": "quote",
        "payload": {"epic": EPIC, "timestamp": 1_784_988_001_234, "bid": 100.1, "ofr": 100.3},
    }
)


async def test_the_loop_connects_subscribes_and_reports_connected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    up, emitted, provider = run_upstream(monkeypatch, [ScriptedSocket()])
    up.start()
    try:
        await until(lambda: any(e.get("state") == "connected" for e in emitted))
    finally:
        await up.stop()

    assert provider.urls == [URL]
    # Subscribed before the room is told the feed is up: a subscriber hearing "connected"
    # and then silence cannot tell a quiet market from a subscription never sent.
    socket = provider.opened[0]
    assert [m["destination"] for m in socket.sent] == [
        "OHLCMarketData.subscribe",
        "marketData.subscribe",
    ]
    assert emitted == [{"kind": "status", "state": "connected"}]


async def test_a_dropped_connection_reconnects_and_resubscribes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    up, emitted, provider = run_upstream(
        monkeypatch, [ScriptedSocket([QUOTE_FRAME], ending="drop"), ScriptedSocket()]
    )
    up.start()
    try:
        await until(lambda: len(provider.opened) == 2)
        await until(lambda: sum(e.get("state") == "connected" for e in emitted) == 2)
    finally:
        await up.stop()

    # A drop over hours is normal. The subscriber should see a gap in prices and a state
    # it can render, not a socket that went quiet and never said so.
    assert [e.get("state") or e["kind"] for e in emitted] == [
        "connected",
        "quote",
        "error",
        "reconnecting",
        "connected",
    ]
    # Resubscribed, not merely reconnected: a fresh socket carries no subscriptions, so a
    # reconnect that skips this reads as a live connection delivering nothing.
    assert [m["destination"] for m in provider.opened[1].sent] == [
        "OHLCMarketData.subscribe",
        "marketData.subscribe",
    ]


async def test_a_reconnect_asks_for_the_session_again(monkeypatch: pytest.MonkeyPatch) -> None:
    handed: list[tuple[str, str]] = []

    async def tokens() -> tuple[str, str]:
        pair = (f"cst-{len(handed)}", f"token-{len(handed)}")
        handed.append(pair)
        return pair

    up, _, provider = run_upstream(
        monkeypatch, [ScriptedSocket(ending="drop"), ScriptedSocket()], tokens=tokens
    )
    up.start()
    try:
        await until(lambda: len(provider.opened) == 2 and bool(provider.opened[1].sent))
    finally:
        await up.stop()

    # The tokens are asked for per session, not captured once. A session outlives about
    # ten idle minutes; reconnecting with the dead pair subscribes to a refusal.
    assert len(handed) == 2
    assert provider.opened[1].sent[0]["cst"] == "cst-1"


async def test_a_failure_before_the_socket_opens_is_reported_not_fatal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    async def tokens() -> tuple[str, str]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("no capital.com session yet")
        return ("cst-value", "token-value")

    up, emitted, provider = run_upstream(monkeypatch, [ScriptedSocket()], tokens=tokens)
    up.start()
    try:
        await until(lambda: any(e.get("state") == "connected" for e in emitted))
    finally:
        await up.stop()

    # Login can be down when the room opens. That is a reason to retry, not a reason for
    # the room to have no feed for the rest of the process's life.
    assert emitted[0]["kind"] == "error"
    assert "no capital.com session" in emitted[0]["message"]
    assert provider.urls == [URL]  # the failed attempt never reached a socket


async def test_stopping_ends_the_loop_without_reporting_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    up, emitted, provider = run_upstream(monkeypatch, [ScriptedSocket()])
    up.start()
    await until(lambda: any(e.get("state") == "connected" for e in emitted))

    await up.stop()
    await asyncio.sleep(0.05)

    # The last subscriber leaving is not a fault. Emitting an error here would publish a
    # failure to a room being torn down, and reconnecting would hold a connection open
    # for an audience that has gone.
    assert len(provider.opened) == 1
    assert [e["kind"] for e in emitted] == ["status"]
    assert up._task is None


async def test_the_keepalive_stops_with_the_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(upstream_module, "PING_INTERVAL_SECONDS", 0.01)
    socket = ScriptedSocket()
    up, _emitted, _ = run_upstream(monkeypatch, [socket])
    up.start()
    await until(lambda: len(socket.sent) > 3)  # subscriptions, then pings

    await up.stop()
    after_stop = len(socket.sent)
    await asyncio.sleep(0.05)

    # A ping task outliving its session pings a socket nobody reads, forever, once per
    # reconnect — the kind of leak that only shows up after hours of uptime.
    assert len(socket.sent) == after_stop
