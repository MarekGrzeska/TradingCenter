"""What the provider says, and what leaves the module as a result.

The translation is tested without a socket: `_on_message` is fed the frames capital.com
sends and the emitted events are collected. The connection itself — connect, subscribe,
reconnect — is exercised by the live smoke tests, because a fake WebSocket would only
prove the fake behaves.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from capital_gateway.dtos import Resolution
from capital_gateway.stream import upstream as upstream_module
from capital_gateway.stream.upstream import Upstream

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
