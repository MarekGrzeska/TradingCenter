"""The client for `market-data` — the one seam every request into the archive passes
through, and so the one place the module's read-only boundary can be enforced once
rather than trusted at every call site.

`_request` is where that happens: a method other than GET is rejected before a socket
ever opens, with one named exception. `POST /indicators/{symbol}` is a computation, not
a write — its method is POST only because the request body does not fit in a URL
(specs/market-mcp-upstream-access, "Do archiwum idą wyłącznie żądania czytające").
"""

from __future__ import annotations

import re

import httpx

from .config import Settings

_INDICATOR_COMPUTE_PATH = re.compile(r"^/indicators/[^/]+$")


class UpstreamWriteRejected(Exception):
    """Raised before any request leaves the process. Not an HTTP error — market-data
    never saw this request and never had a chance to refuse it itself."""


class UpstreamClient:
    def __init__(self, settings: Settings) -> None:
        self._http = httpx.AsyncClient(
            base_url=settings.market_data_url,
            timeout=settings.market_data_request_timeout_seconds,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get(self, path: str, params: dict | None = None) -> httpx.Response:
        return await self._request("GET", path, params=params)

    async def compute_indicators(self, symbol: str, body: dict) -> httpx.Response:
        return await self._request("POST", f"/indicators/{symbol}", json=body)

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        is_read = method == "GET" or (method == "POST" and _INDICATOR_COMPUTE_PATH.match(path))
        if not is_read:
            raise UpstreamWriteRejected(
                f"{method} {path} is not a read. market-mcp calls market-data to read "
                "and to compute indicators, never to write — see "
                'specs/market-mcp-upstream-access, "Do archiwum idą wyłącznie żądania '
                'czytające".'
            )
        return await self._http.request(method, path, **kwargs)
