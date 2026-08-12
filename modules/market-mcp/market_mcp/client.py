"""The client for `market-data` — the one seam every request into the archive passes
through, and so the one place the module's read-only boundary can be enforced once
rather than trusted at every call site.

`_request` is where that happens: a method other than GET is rejected before a socket
ever opens, with one named exception. `POST /indicators/{symbol}` is a computation, not
a write — its method is POST only because the request body does not fit in a URL
(specs/market-mcp-upstream-access, "Do archiwum idą wyłącznie żądania czytające").

Task 5.1's outbound identity lives here too: `market_data_scope` set means every
request carries a bearer token from this process's own managed identity, fetched fresh
per request — `DefaultAzureCredential` caches internally and only reaches the identity
endpoint again once the cached token is close to expiring, so this is not one round
trip per call (same reasoning `market_data/db.py`'s `_TokenProvider` documents for the
database side of this pattern).
"""

from __future__ import annotations

import asyncio
import logging
import re

import httpx
from azure.identity.aio import DefaultAzureCredential

from .config import Settings
from .errors import ToolRefusal

log = logging.getLogger(__name__)

_INDICATOR_COMPUTE_PATH = re.compile(r"^/indicators/[^/]+$")

# A burst of concurrent tool calls is a burst of concurrent requests to market-data —
# bounded here rather than left open, the same reasoning market-data's own
# `indicator_concurrency` gate uses on its side of this same seam.
MAX_CONCURRENT_UPSTREAM_REQUESTS = 8


class UpstreamWriteRejected(Exception):
    """Raised before any request leaves the process. Not an HTTP error — market-data
    never saw this request and never had a chance to refuse it itself."""


class UpstreamClient:
    def __init__(self, settings: Settings) -> None:
        self._http = httpx.AsyncClient(
            base_url=settings.market_data_url,
            timeout=settings.market_data_request_timeout_seconds,
        )
        self._timeout_seconds = settings.market_data_request_timeout_seconds
        self._gate = asyncio.Semaphore(MAX_CONCURRENT_UPSTREAM_REQUESTS)

        self._scope = settings.market_data_scope
        self._credential = DefaultAzureCredential() if self._scope else None
        if self._scope:
            log.info("authenticating to market-data with a managed identity, scope=%s", self._scope)

    async def aclose(self) -> None:
        await self._http.aclose()
        if self._credential is not None:
            await self._credential.close()

    async def _auth_headers(self) -> dict[str, str]:
        if self._credential is None or self._scope is None:
            return {}
        try:
            token = await self._credential.get_token(self._scope)
        except Exception as err:
            # Not retried and not papered over with a fallback — one does not exist.
            # Whatever this raises propagates up as the tool's refusal.
            raise ToolRefusal(f"could not obtain a credential for market-data: {err}") from err
        return {"Authorization": f"Bearer {token.token}"}

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
        async with self._gate:
            response = await self._send(method, path, **kwargs)
            # One retry: a 5xx is market-data's own trouble, not a malformed
            # request, and every request through this client is a read — retrying
            # duplicates nothing (specs/market-mcp-upstream-access, "Wołanie archiwum
            # ma skończony czas i jedno ponowienie").
            if response.status_code >= 500:
                response = await self._send(method, path, **kwargs)
        return response

    async def _send(self, method: str, path: str, **kwargs) -> httpx.Response:
        auth_headers = await self._auth_headers()
        if auth_headers:
            kwargs["headers"] = {**kwargs.get("headers", {}), **auth_headers}
        try:
            return await self._http.request(method, path, **kwargs)
        except httpx.TimeoutException as err:
            raise ToolRefusal(
                f"market-data did not respond within {self._timeout_seconds}s. This "
                "is a failure on this module's side, not missing data."
            ) from err
        except httpx.RequestError as err:
            raise ToolRefusal(f"market-data is unreachable: {err}") from err
