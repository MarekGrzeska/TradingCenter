"""Smoke tests against the real capital.com demo API.

Skipped unless ``--run-live`` is passed and credentials are configured. These are the
only tests that can catch a provider changing its mind — the rest of the suite proves
this module is consistent with what capital.com did in July 2026, which is not the same
claim.

Read-only. Nothing here places, amends or cancels an order — that lives in
``test_live_trading.py`` behind its own flag, so this file stays safe to run against any
demo account at any time.
"""

from __future__ import annotations

import asyncio

import pytest

from capital_gateway.adapter import CapitalAdapter
from capital_gateway.client import CapitalClient
from capital_gateway.config import Settings
from capital_gateway.dtos import Resolution
from capital_gateway.stream.hub import Hub
from capital_gateway.stream.messages import CandleMessage, Message, QuoteMessage
from capital_gateway.stream.upstream import Upstream

pytestmark = pytest.mark.live

EPIC = "US100"  # liquid enough that quotes arrive within seconds while the market is open


async def test_a_session_opens_and_accounts_are_readable(settings: Settings) -> None:
    adapter = CapitalAdapter(CapitalClient(settings))
    try:
        accounts = await adapter.list_accounts()
        assert accounts
        assert sum(a.active for a in accounts) == 1
    finally:
        await adapter.aclose()


async def test_a_deep_read_pages_and_reports_its_cost(settings: Settings) -> None:
    adapter = CapitalAdapter(CapitalClient(settings))
    try:
        result = await adapter.get_history(EPIC, Resolution.MINUTE_5, 2500)

        # More than one request by construction: the provider's ceiling is 1000.
        assert result.requests >= 3
        stamps = [c.ts for c in result.candles]
        assert stamps == sorted(stamps)
        assert len(set(stamps)) == len(stamps)
        # Either the request was satisfied, or the instrument said why it was not.
        assert result.count == 2500 or result.history_ended
    finally:
        await adapter.aclose()


async def _watch(
    settings: Settings, resolution: Resolution, until: str, timeout: float
) -> list[Message]:
    """Subscribe and collect until a message of ``until`` kind arrives, or time out."""
    client = CapitalClient(settings)
    received: list[Message] = []
    arrived = asyncio.Event()

    async def tokens() -> tuple[str, str]:
        if not client.authenticated:
            await client.login()
        return client.stream_tokens()

    async def subscriber(message: Message) -> None:
        received.append(message)
        if until == "quote" and isinstance(message, QuoteMessage):
            arrived.set()
        if until == "sealed" and isinstance(message, CandleMessage) and not message.forming:
            arrived.set()

    hub = Hub(
        lambda epic, res, emit: Upstream(settings.capital_stream_url, epic, res, tokens, emit)
    )
    try:
        await hub.subscribe(EPIC, resolution, subscriber)
        try:
            await asyncio.wait_for(arrived.wait(), timeout=timeout)
        except TimeoutError:
            pytest.skip(
                f"no {until} for {EPIC} within {timeout:.0f}s — the market is probably closed"
            )
        return received
    finally:
        await hub.aclose()
        await client.aclose()


async def test_the_stream_delivers_quotes_and_a_forming_candle(settings: Settings) -> None:
    received = await _watch(settings, Resolution.MINUTE_5, until="quote", timeout=30)

    quotes = [m for m in received if isinstance(m, QuoteMessage)]
    assert quotes[0].bid > 0
    assert quotes[0].ask >= quotes[0].bid

    # A quote must have produced a forming candle — that is the whole point of
    # assembling one server-side.
    candles = [m for m in received if isinstance(m, CandleMessage)]
    assert candles
    assert candles[-1].forming is True


async def test_the_stream_delivers_a_sealed_candle(settings: Settings) -> None:
    """MINUTE rather than MINUTE_5, because a sealed candle only arrives when a period
    ends and this test would otherwise sit for five minutes. Even at one minute it can
    wait most of one, which is why it is opt-in and skips rather than fails."""
    received = await _watch(settings, Resolution.MINUTE, until="sealed", timeout=90)

    sealed = [m for m in received if isinstance(m, CandleMessage) and not m.forming]
    assert sealed
    candle = sealed[-1]
    assert candle.low <= candle.open <= candle.high
    assert candle.low <= candle.close <= candle.high
    # Published once per period despite the provider sending both price sides.
    assert len({c.time for c in sealed}) == len(sealed)
