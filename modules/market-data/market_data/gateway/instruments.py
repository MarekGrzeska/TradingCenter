"""Asking the gateway whether a pair is worth collecting.

The archive does not own the instrument catalogue and should not keep a copy of it: the
gateway does, the provider changes it, and a second list here would be wrong within a
week. So a pair offered by an operator is checked against the thing that would actually
have to serve it.

The check is "can one candle be had for this symbol at this resolution", not "does this
symbol appear in a search". A search matches on names and would happily accept an
instrument the provider has no price series for at that resolution — which is a pair that
sits on the tracked list forever, holding a provider connection and archiving nothing.
"""

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
        """Whether the gateway can produce candles for this pair right now.

        One candle is asked for, which is one provider request — the cheapest question
        that has the right answer. `False` means the pair exists as far as the request
        went but has no series; a symbol the provider does not know at all comes back as
        `GatewayRefused`, and the caller can tell an operator which of the two it was.
        """
        candles = await get_json(
            self._client,
            f"{self._base_url}/instruments/{symbol}/candles",
            params={"resolution": resolution.value, "limit": 1},
            what=f"candles for {symbol}",
        )
        return isinstance(candles, list) and len(candles) > 0

    async def is_market_open(self, symbol: str) -> bool | None:
        """Whether the provider currently calls this instrument tradeable.

        The archive has no session calendar and will not grow one — inventing a market's
        opening hours produces a confident wrong answer twice a day. This asks the module
        that already knows, and `None` — no exact match in the catalogue — stays distinct
        from `False`, because "could not find out" and "the market is shut" send an
        operator to two different places.

        Read off the search route because the gateway publishes none for a single
        instrument, and matched on the symbol **exactly**: search matches names as well as
        symbols, so its first hit for `GOLD` is not guaranteed to be `GOLD`.
        """
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

    # --- specs/market-data-api: the catalogue itself, proxied for the terminal --------
    #
    # capital-gateway is not public — the terminal cannot reach it directly (design.md,
    # "Terminal osiąga katalog instrumentów przez market-data"). These three forward the
    # gateway's own JSON unread: no model, no reshaping, so a field the gateway adds is
    # visible here the same day rather than on the next release of this module.

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
