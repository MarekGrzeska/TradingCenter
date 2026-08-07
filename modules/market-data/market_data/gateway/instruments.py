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

from ..errors import GatewayRefused, GatewayUnreachable, UnreadablePayload
from ..models import Resolution


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
        url = f"{self._base_url}/instruments/{symbol}/candles"
        params = {"resolution": resolution.value, "limit": 1}

        try:
            response = await self._client.get(url, params=params)
        except httpx.RequestError as err:
            raise GatewayUnreachable(
                f"the gateway did not answer when asked about {symbol}: {err}"
            ) from err

        if response.is_error:
            raise GatewayRefused(response.status_code, _detail(response))

        try:
            candles = response.json()
        except ValueError as err:
            raise UnreadablePayload(
                f"the gateway's candles for {symbol} were not JSON: {err}"
            ) from err

        return isinstance(candles, list) and len(candles) > 0


def _detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text.strip() or response.reason_phrase
    if isinstance(body, dict) and isinstance(body.get("detail"), str):
        return body["detail"]
    return str(body)
