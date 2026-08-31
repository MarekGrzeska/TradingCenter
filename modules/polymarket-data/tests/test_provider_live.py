"""The measurements this module's design rests on, run against the real provider. `live`, so CI never
runs them — and they exist because a fact that is built on and never measured again has a date on it."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from polymarket_data import parsing, provider

pytestmark = pytest.mark.live


@pytest.fixture
async def client():
    async with provider.client(
        gamma_base_url="https://gamma-api.polymarket.com",
        clob_base_url="https://clob.polymarket.com",
        user_agent="tradingcenter-polymarket-data/0.1 (tests)",
        concurrency=4,
    ) as built:
        yield built


async def a_liquid_event(client: provider.PolymarketClient) -> dict:
    """Something being traded right now, with few enough markets to check by hand."""
    listing = await client.browse_events(order="volume24hr", limit=25)
    for payload in listing:
        markets = payload.get("markets") or []
        if 1 <= len(markets) <= 4:
            return payload
    return listing[0]


async def test_the_metadata_surface_publishes_the_order_books_midpoint(client) -> None:
    """The measurement the sampler rests on, and the one worth re-running: `outcomePrices` was the order
    book's midpoint to the digit. A tolerance rather than equality, since the two are read a moment apart."""
    payload = await a_liquid_event(client)
    prices = parsing.prices_from(payload)
    assert prices, "the event carried no prices at all"

    checked = 0
    for token_id, (midpoint, _) in list(prices.items())[:6]:
        if midpoint is None:
            continue
        from_book = await client.midpoint(token_id)
        assert from_book is not None, f"the order book has no midpoint for {token_id}"
        assert abs(from_book - midpoint) <= 0.02, (
            f"{token_id}: metadata says {midpoint}, the order book says {from_book}. "
            "The sampler takes its prices from the metadata surface because these two "
            "agreed when it was written; they no longer do."
        )
        checked += 1
    assert checked >= 2, "not enough priced outcomes to check anything"


async def test_the_history_window_is_still_fifteen_days(client) -> None:
    """Measured 22 August 2026: 15 days accepted, 16 refused, and the cap is on the interval. A provider
    that moved it would leave every backfill refused with nothing saying why."""
    payload = await a_liquid_event(client)
    token = next(iter(parsing.prices_from(payload)))
    now = datetime.now(UTC)

    fifteen = await client.price_history(
        token, since=now - timedelta(days=15), until=now
    )
    assert isinstance(fifteen, list)

    with pytest.raises(provider.ProviderRefused, match="too long"):
        await client.price_history(token, since=now - timedelta(days=16), until=now)


async def test_the_answer_runs_past_the_window_that_was_asked_for(client) -> None:
    """`endTs` is not honoured — measured — which is why both edges are checked when a
    sample is written rather than trusted to the request."""
    payload = await a_liquid_event(client)
    token = next(iter(parsing.prices_from(payload)))
    now = datetime.now(UTC)
    until = now - timedelta(days=1)

    points = await client.price_history(token, since=until - timedelta(hours=6), until=until)

    assert points, "no history at all for a liquid market"
    newest = datetime.fromtimestamp(points[-1][0], UTC)
    assert newest > until, (
        "the provider honoured endTs. If that is now reliable, the clipping in "
        "ingest._fill_window is still correct but no longer the only thing keeping "
        "'collected' honest — say so there before removing it."
    )


async def test_the_edge_still_selects_on_the_user_agent(client) -> None:
    """Why `PROVIDER_USER_AGENT` exists, stated exactly. The first version of this measurement was wrong:
    what drew the 403 was `urllib`'s own default, not an absent header — the edge *selects* on it."""
    async with httpx.AsyncClient(timeout=30.0) as bare:
        url = "https://gamma-api.polymarket.com/events"
        refused = await bare.get(
            url, params={"limit": 1}, headers={"user-agent": "Python-urllib/3.12"}
        )
        served = await bare.get(
            url, params={"limit": 1}, headers={"user-agent": "tradingcenter-polymarket-data/0.1"}
        )

    assert served.status_code == 200, "the provider refused a request naming this module"
    assert refused.status_code == 403, (
        "the edge no longer refuses urllib's default. PROVIDER_USER_AGENT may have stopped "
        "being load-bearing — worth knowing before someone deletes it, and worth correcting "
        "in design.md rather than leaving a measurement that is no longer true."
    )
