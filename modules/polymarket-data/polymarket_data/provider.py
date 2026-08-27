"""The only door to Polymarket, which needs no credential but whose edge refuses some library defaults on `User-Agent`.
Three refusals are told apart — nothing, declined, unreadable — because none may reach a consumer as "no data"."""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal

import httpx

from . import parsing
from .models import Event

log = logging.getLogger(__name__)

# Measured 22 August 2026: 15 days between `startTs` and `endTs` is accepted and 16 is refused. The cap
# is on the *interval*, not the point count, so a coarser `fidelity` buys no more of it.
MAX_HISTORY_WINDOW_DAYS = 15

# How long to wait before the whole read is a failure. Generous rather than tight: this is a
# third party's availability, and a backfill window is a large response.
REQUEST_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class ProviderError(Exception):
    """Anything that stopped this module getting an answer."""


class ProviderHasNothing(ProviderError):
    """The provider answered, and the answer is that it has no such thing — an answer to the question,
    not a failure of this module: one means "tell the operator", the other "try again"."""


class ProviderRefused(ProviderError):
    """The provider declined — a rate limit, a bad request, or its own failure."""


ProviderUnusable = parsing.ProviderPayloadUnusable


class PolymarketClient:
    """Both of the provider's surfaces, with one budget between them. One semaphore, not one per surface:
    two gates sharing a number would still let a deep backfill starve the sampler."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        gamma_base_url: str,
        clob_base_url: str,
        concurrency: int,
        max_attempts: int = 4,
    ) -> None:
        self._client = client
        self._gamma = gamma_base_url.rstrip("/")
        self._clob = clob_base_url.rstrip("/")
        self._gate = asyncio.Semaphore(concurrency)
        self._max_attempts = max_attempts

    async def _get(self, url: str, params: dict | None = None) -> dict | list:
        """One read, with the budget and the backoff around it. Retries only what says nothing about
        whether the request was handled; a 404 is an answer, and retrying it would spend the budget."""
        delay = 0.5
        for attempt in range(1, self._max_attempts + 1):
            async with self._gate:
                try:
                    response = await self._client.get(url, params=params)
                except httpx.HTTPError as err:
                    if attempt == self._max_attempts:
                        raise ProviderRefused(f"{url} could not be reached: {err}") from err
                    log.warning("provider unreachable (%s), attempt %d", err, attempt)
                else:
                    if response.status_code == 404:
                        raise ProviderHasNothing(f"{url} — the provider has no such thing")
                    if response.status_code < 400:
                        try:
                            return response.json()
                        except ValueError as err:
                            raise ProviderUnusable(
                                f"{url} answered {response.status_code} with a body that is "
                                "not JSON"
                            ) from err
                    if response.status_code not in (429, 500, 502, 503, 504):
                        # A refusal that will be refused again — a malformed request, most often the
                        # 15-day window exceeded. Raised with the provider's own words.
                        raise ProviderRefused(
                            f"{url} refused with {response.status_code}: "
                            f"{response.text[:200]}"
                        )
                    if attempt == self._max_attempts:
                        raise ProviderRefused(
                            f"{url} kept answering {response.status_code} after "
                            f"{attempt} attempts"
                        )
                    log.warning(
                        "provider answered %s, backing off (attempt %d)",
                        response.status_code,
                        attempt,
                    )
            # Slept outside the semaphore, so a backing-off request holds no place in the budget.
            # Jittered, because several outcomes of one event back off together.
            await asyncio.sleep(delay + random.uniform(0, delay / 2))
            delay *= 2
        raise ProviderRefused(f"{url} was not answered")

    async def event_by_reference(self, reference: str) -> Event:
        """An event by its address or by its slug — one observation, not two code paths."""
        slug = parsing.slug_from(reference)
        payload = await self._get(f"{self._gamma}/events/slug/{slug}")
        if not isinstance(payload, dict):
            raise ProviderUnusable(f"the provider's answer for {slug!r} is not an event")
        return parsing.event_from(payload)

    async def event_by_id(self, provider_event_id: str) -> Event:
        payload = await self._get(f"{self._gamma}/events/{provider_event_id}")
        if not isinstance(payload, dict):
            raise ProviderUnusable(
                f"the provider's answer for event {provider_event_id!r} is not an event"
            )
        return parsing.event_from(payload)

    async def event_payload(self, provider_event_id: str) -> dict:
        """The raw event, for the sampler. Raw rather than parsed because this is the request that
        prices the whole event, and `parsing.prices_from` is what reads it."""
        payload = await self._get(f"{self._gamma}/events/{provider_event_id}")
        if not isinstance(payload, dict):
            raise ProviderUnusable(
                f"the provider's answer for event {provider_event_id!r} is not an event"
            )
        return payload

    async def search_events(self, query: str, *, limit: int = 10) -> list[dict]:
        """The provider's public database, by phrase. Live, and never written down."""
        payload = await self._get(
            f"{self._gamma}/public-search", {"q": query, "limit_per_type": limit}
        )
        if isinstance(payload, dict):
            events = payload.get("events") or []
            return [event for event in events if isinstance(event, dict)]
        return []

    async def browse_events(
        self,
        *,
        tag_id: str | None = None,
        order: str = "volume24hr",
        ascending: bool = False,
        limit: int = 20,
        offset: int = 0,
        closed: bool = False,
    ) -> list[dict]:
        """The public database by category rather than by phrase — a model asked about a subject has no
        phrase to guess with. The slimming is this module's: a listing of a hundred events measured 10 MiB."""
        params: dict[str, object] = {
            "limit": limit,
            "offset": offset,
            "order": order,
            "ascending": str(ascending).lower(),
            "closed": str(closed).lower(),
        }
        if tag_id:
            params["tag_id"] = tag_id
        payload = await self._get(f"{self._gamma}/events", params)
        return [event for event in payload if isinstance(event, dict)] if isinstance(
            payload, list
        ) else []

    async def price_history(
        self, token_id: str, *, since: datetime, until: datetime, fidelity_minutes: int = 1
    ) -> list[tuple[int, Decimal]]:
        """One outcome's series for one window, oldest first. Two measured, undocumented things: the
        window may not exceed fifteen days, and `endTs` is not honoured, so the caller clips both ways."""
        payload = await self._get(
            f"{self._clob}/prices-history",
            {
                "market": token_id,
                "startTs": int(since.timestamp()),
                "endTs": int(until.timestamp()),
                "fidelity": fidelity_minutes,
            },
        )
        if not isinstance(payload, dict):
            raise ProviderUnusable(f"the price history for {token_id} is not an object")
        return parsing.history_points(payload)

    async def midpoint(self, token_id: str) -> Decimal | None:
        """One outcome's book midpoint, straight from the order book. The sampler does not use this; it
        stays as the checking path, because the equivalence the sampler rests on is measured."""
        payload = await self._get(f"{self._clob}/midpoint", {"token_id": token_id})
        if not isinstance(payload, dict):
            return None
        try:
            return Decimal(str(payload["mid"]))
        except (KeyError, ValueError, ArithmeticError):
            return None


@asynccontextmanager
async def client(
    *, gamma_base_url: str, clob_base_url: str, user_agent: str, concurrency: int
) -> AsyncIterator[PolymarketClient]:
    """The client and the connection pool under it, closed on the way out. The `User-Agent` is set here
    once: a request that forgets it fails in a way that reads like an address block."""
    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": user_agent, "Accept": "application/json"},
        follow_redirects=True,
    ) as http:
        yield PolymarketClient(
            http,
            gamma_base_url=gamma_base_url,
            clob_base_url=clob_base_url,
            concurrency=concurrency,
        )
