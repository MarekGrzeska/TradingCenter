"""Smoke tests against the real capital.com demo API, skipped without ``--run-live``. Read-only:
the writes live in ``test_live_trading.py``, so this stays safe against any demo account."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

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


async def test_the_gate_keeps_a_burst_under_the_providers_limit(settings: Settings) -> None:
    """Whether capital.com agrees the resulting stream of requests is acceptable — a rate limit in
    production is not an exception but an empty candle series. Waits out the previous test's traffic."""
    burst = 25  # more than two windows at 10/s, so the gate has to hold the line twice
    client = CapitalClient(settings)
    try:
        await client.login()  # not part of the burst, and not part of the timing
        await asyncio.sleep(1.1)  # let the provider's window drain

        started = time.monotonic()
        responses = await asyncio.gather(*(client.session_details() for _ in range(burst)))
        elapsed = time.monotonic() - started

        assert [r.status_code for r in responses if r.status_code != 200] == []
        # 25 requests cannot clear a 10-per-second gate in under two seconds. Passing faster
        # would mean the gate let the burst through, and the assertion above would be luck.
        assert elapsed >= 2.0
    finally:
        await client.aclose()


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
    """MINUTE rather than MINUTE_5: a sealed candle only arrives when a period ends, and this would
    otherwise sit for five minutes. It can still wait most of one, which is why it is opt-in."""
    received = await _watch(settings, Resolution.MINUTE, until="sealed", timeout=90)

    sealed = [m for m in received if isinstance(m, CandleMessage) and not m.forming]
    assert sealed
    candle = sealed[-1]
    assert candle.low <= candle.open <= candle.high
    assert candle.low <= candle.close <= candle.high
    # Published once per period despite the provider sending both price sides.
    assert len({c.time for c in sealed}) == len(sealed)


# Three things this module depends on, none of them documented by capital.com. Read-only and cheap,
# so a provider changing its mind is a red test here rather than a wrong candle in an archive.


def _newest_period_start(history_ts: str) -> datetime:
    """The provider's stamp, read the way `history.parse_candle_ts` reads it."""
    parsed = datetime.fromisoformat(history_ts.rstrip("Z"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


async def test_a_history_read_reaching_now_includes_the_period_still_running(
    settings: Settings,
) -> None:
    """The newest candle of a read that reaches the present belongs to a period not yet finished.
    `market-data` stored it as settled until this was measured, on a comment asserting the opposite."""
    adapter = CapitalAdapter(CapitalClient(settings))
    try:
        instruments = await adapter.search_instruments(EPIC)
        if not any(i.symbol == EPIC and i.tradeable for i in instruments):
            pytest.skip("US100 is shut; the period still running is the point of this test")

        candles = await adapter.get_candles(EPIC, Resolution.MINUTE_5, 3)
        assert candles

        newest = _newest_period_start(candles[-1].ts)
        bucket = datetime.now(UTC).timestamp() // 300 * 300
        assert newest.timestamp() == bucket, (
            "the newest candle is not the period we are in — the provider serves only "
            "settled candles after all, and `forming` may be a constant here"
        )
    finally:
        await adapter.aclose()


async def test_a_daily_read_reaching_now_includes_today(settings: Settings) -> None:
    """The same claim for DAY, which arithmetic cannot check: a daily boundary follows the venue's
    session. The weaker check is the honest one — today's candle is present while the market is open."""
    adapter = CapitalAdapter(CapitalClient(settings))
    try:
        instruments = await adapter.search_instruments(EPIC)
        if not any(i.symbol == EPIC and i.tradeable for i in instruments):
            pytest.skip("US100 is shut; nothing is running to observe")

        candles = await adapter.get_candles(EPIC, Resolution.DAY, 3)
        assert candles

        newest = _newest_period_start(candles[-1].ts)
        assert newest.date() == datetime.now(UTC).date(), (
            "no candle for today while the market is open — the daily period being "
            "served is one that already closed, and the stream cannot be seeded from it"
        )
    finally:
        await adapter.aclose()


async def test_market_status_tracks_the_session(settings: Settings) -> None:
    """`tradeable` decides whether a daily candle is still forming, so it has to mean the session
    and not merely "this instrument exists". Measured against the quotes, the same fact observed."""
    adapter = CapitalAdapter(CapitalClient(settings))
    try:
        instruments = await adapter.search_instruments(EPIC)
        found = [i for i in instruments if i.symbol == EPIC]
        assert found, "US100 is not in the provider's catalogue"
        tradeable = found[0].tradeable
    finally:
        await adapter.aclose()

    received = await _watch(settings, Resolution.MINUTE_5, until="quote", timeout=20)
    quoted = any(isinstance(m, QuoteMessage) for m in received)

    assert quoted == tradeable, (
        f"the catalogue says tradeable={tradeable} and the stream "
        f"{'delivered' if quoted else 'delivered no'} quotes; one of the two is not "
        "about the session"
    )
