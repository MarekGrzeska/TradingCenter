"""Stand-ins for the provider, so ingest can be tested without a third party's uptime.

Structural rather than a subclass: what `Ingest` uses is three methods, and a Protocol per
seam would buy nothing the tests do not already prove by running.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal

from polymarket_data import provider


def event_payload(
    provider_event_id: str = "e-1",
    *,
    slug: str = "an-event",
    markets: tuple[dict, ...] | None = None,
) -> dict:
    return {
        "id": provider_event_id,
        "slug": slug,
        "title": slug.replace("-", " ").title(),
        "markets": list(markets or (market_payload(),)),
    }


def market_payload(
    market_id: str = "m-1",
    *,
    outcomes: tuple[str, ...] = ("Yes", "No"),
    prices: tuple[str, ...] = ("0.6", "0.4"),
    last_trade: str | None = "0.59",
    closed: bool = False,
) -> dict:
    payload = {
        "id": market_id,
        "question": "Will it?",
        "outcomes": json.dumps(list(outcomes)),
        "clobTokenIds": json.dumps([f"{market_id}-t{i}" for i in range(len(outcomes))]),
        "outcomePrices": json.dumps(list(prices)),
        "closed": closed,
    }
    if last_trade is not None:
        payload["lastTradePrice"] = last_trade
    return payload


class FakeProvider:
    """Answers from a script. `payloads` maps a provider event id to what it returns, or to
    an exception to raise."""

    def __init__(
        self,
        payloads: dict[str, dict | Exception] | None = None,
        history: dict[str, list[tuple[int, str]]] | None = None,
    ) -> None:
        self.payloads = payloads or {}
        self.history = history or {}
        self.event_calls: list[str] = []
        self.history_calls: list[tuple[str, datetime, datetime]] = []

    async def event_payload(self, provider_event_id: str) -> dict:
        self.event_calls.append(provider_event_id)
        answer = self.payloads.get(provider_event_id)
        if isinstance(answer, Exception):
            raise answer
        if answer is None:
            raise provider.ProviderHasNothing(provider_event_id)
        return answer

    async def price_history(
        self, token_id: str, *, since: datetime, until: datetime, fidelity_minutes: int = 1
    ) -> list[tuple[int, Decimal]]:
        self.history_calls.append((token_id, since, until))
        answer = self.history.get(token_id, [])
        if isinstance(answer, Exception):
            raise answer
        return [(moment, Decimal(price)) for moment, price in answer]
