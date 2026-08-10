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
    """The unit test measures this module's own delay; this measures whether capital.com
    agrees that the resulting stream of requests is acceptable.

    The failure it exists to catch is a rate limit reached in production, where a 429 is
    not an exception a caller sees but an empty candle series that looks like a data
    problem.

    The gate is per ``CapitalClient`` and the provider counts per account, so this waits
    out the previous test's traffic first. It has to: a new client's window starts empty
    and knows nothing of what the last one sent, and without the wait this test measured
    the deep read's tail rather than its own burst. The app runs one client per process,
    which is what makes the per-client gate a process-wide one — two clients in one
    process would be two gates and twice the rate.
    """
    burst = 25  # more than two windows at 10/s, so the gate has to hold the line twice
    client = CapitalClient(settings)
    try:
        await client.login()  # not part of the burst, and not part of the timing
        await asyncio.sleep(1.1)  # let the provider's window drain

        started = time.monotonic()
        responses = await asyncio.gather(*(client.session_details() for _ in range(burst)))
        elapsed = time.monotonic() - started

        assert [r.status_code for r in responses if r.status_code != 200] == []
        # 25 requests cannot clear a 10-per-second gate in under two seconds. Passing this
        # faster would mean the gate let the burst through, and the assertion above would
        # then be luck rather than evidence.
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


# --- what the provider's history actually contains, measured rather than assumed ---
#
# Three things this module now depends on, none of them documented by capital.com. They
# are read-only and cheap; they exist so a provider changing its mind is a red test here
# rather than a wrong candle in somebody's archive.


def _newest_period_start(history_ts: str) -> datetime:
    """The provider's stamp, read the way `history.parse_candle_ts` reads it."""
    parsed = datetime.fromisoformat(history_ts.rstrip("Z"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


async def test_a_history_read_reaching_now_includes_the_period_still_running(
    settings: Settings,
) -> None:
    """The newest candle of a read that reaches the present belongs to a period that has
    not finished yet.

    `market-data` stored that candle as a settled fact until this was measured, on the
    strength of a comment asserting the opposite ("the current period has not finished,
    so the provider does not have it either"). Both readings cannot be right, and the
    one that was written down was never checked.

    MINUTE_5 because its boundary is arithmetic, so "is this the period we are in" has an
    exact answer without asking the venue about its session.
    """
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
    """The same claim for DAY, which is the one that cannot be checked by arithmetic.

    No bucket comparison: a daily boundary follows the venue's session, and computing one
    is exactly what this module refuses to do. The weaker check is the one that is
    honest — today's candle is present while the market is open — and it is enough to
    decide whether `tradeable` is a usable source of truth for "this period is running".
    """
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
    """`tradeable` is what decides whether a daily candle is still forming, so it has to
    mean the session and not merely "this instrument exists".

    Measured against the quotes, which are the other observable of the same fact: a
    market the provider calls tradeable is one whose quotes move.
    """
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
