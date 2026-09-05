"""Asking the gateway whether a pair is worth collecting. The check is "can one candle be had", not
"does this appear in a search": a search matches names and would accept a pair with no series."""

from __future__ import annotations

import httpx

from ..errors import UnreadablePayload
from ..models import Resolution
from ._http import get_json


class GatewayInstruments:
    def __init__(self, base_url: str, client: httpx.AsyncClient) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client

    async def is_collectable(self, symbol: str, resolution: Resolution) -> bool:
        """Whether the gateway can produce candles for this pair right now. One candle is the cheapest
        question with the right answer; a symbol the provider does not know comes back refused instead."""
        candles = await get_json(
            self._client,
            f"{self._base_url}/instruments/{symbol}/candles",
            params={"resolution": resolution.value, "limit": 1},
            what=f"candles for {symbol}",
        )
        return isinstance(candles, list) and len(candles) > 0

    async def is_market_open(self, symbol: str) -> bool | None:
        """Whether the provider currently calls this instrument tradeable. The archive has no session
        calendar and will not grow one; `None` stays distinct from `False`. Matched on the symbol exactly."""
        hits = await get_json(
            self._client,
            f"{self._base_url}/instruments/search",
            params={"q": symbol},
            what=f"whether {symbol} is open",
        )
        if not isinstance(hits, list):
            raise UnreadablePayload(f"the gateway's search for {symbol} was not a list")

        for hit in hits:
            if isinstance(hit, dict) and hit.get("symbol") == symbol:
                tradeable = hit.get("tradeable")
                return tradeable if isinstance(tradeable, bool) else None
        return None

    # capital-gateway is not public, so the terminal reaches the catalogue through here. These three
    # forward the gateway's own JSON unread: a field it adds is visible the same day.

    async def catalogue(self, max_nodes: int | None, asset_class: str | None) -> dict:
        params: dict[str, int | str] = {}
        if max_nodes is not None:
            params["max_nodes"] = max_nodes
        if asset_class is not None:
            params["asset_class"] = asset_class
        return await get_json(
            self._client, f"{self._base_url}/instruments", params=params, what="the catalogue"
        )

    async def search(self, q: str) -> list:
        body = await get_json(
            self._client,
            f"{self._base_url}/instruments/search",
            params={"q": q},
            what="a search",
        )
        if not isinstance(body, list):
            raise UnreadablePayload("the gateway's search response was not a list")
        return body

    async def asset_classes(self) -> list:
        body = await get_json(
            self._client, f"{self._base_url}/asset-classes", params={}, what="the asset classes"
        )
        if not isinstance(body, list):
            raise UnreadablePayload("the gateway's asset classes were not a list")
        return body
