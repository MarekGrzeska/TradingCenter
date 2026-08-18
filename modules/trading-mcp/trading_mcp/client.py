"""The one seam every call to `capital-gateway` passes through, and the demo-only
guard that sits in front of every write.

Reads retry once on a `5xx` — the same rule `market-data`'s and `market-mcp`'s own
upstream clients use for the same reason: a `5xx` is the gateway's own trouble, not a
malformed request, and repeating a read duplicates nothing. Writes never retry:
`capital-gateway` accepts no idempotency key, so a repeated write is a second position,
not a confirmed first one (specs/trading-mcp-execution, "Moduł nie ponawia zlecenia po
własnej awarii").
"""

from __future__ import annotations

import httpx
from tc_mcp_kit.detail import detail

from .config import Settings
from .errors import GatewayRefused, GatewayUnavailable, NotDemoEnvironment

# Matches `capital_gateway/config.py`'s `API_KEY_HEADER` and `market_data/gateway/
# history.py`'s own copy of the same constant. Duplicated rather than imported — no
# shared library between modules (architecture.md, "Why no shared library").
GATEWAY_KEY_HEADER = "X-Gateway-Key"

DEMO_ENVIRONMENT = "demo"


class GatewayClient:
    def __init__(self, settings: Settings) -> None:
        self._http = httpx.AsyncClient(
            base_url=settings.capital_gateway_url,
            timeout=settings.capital_gateway_request_timeout_seconds,
            headers={GATEWAY_KEY_HEADER: settings.capital_gateway_api_key},
        )
        self._timeout_seconds = settings.capital_gateway_request_timeout_seconds

    async def aclose(self) -> None:
        await self._http.aclose()

    async def ensure_demo_environment(self) -> None:
        """Refuse to proceed unless the gateway confirms it is bound to the demo account.

        Asked once, before the port opens (`__main__`), and not again. It used to be
        re-asked before every write, behind a three-state cache invalidated by every
        error the gateway ever returned — which cost a second round trip on every write
        after any 503, for as long as the process lived, and could not detect what it
        was there for: the field it compares was a literal in the gateway's own source
        until 18 August 2026, so it only ever proved the gateway was answering.

        What stands in its place is two things that can each come out differently: the
        gateway derives `environment` from the host it is bound to and refuses to start
        on any host but the demo one, and this module refuses to open a port until it
        has read that answer. What is no longer covered is a gateway swapped underneath
        a running process for one reporting another environment — see
        `openspec/changes/hot-paths-stop-paying-twice/design.md`, D4.
        """
        payload = await self.get("/capabilities")
        environment = payload.get("environment")
        if environment != DEMO_ENVIRONMENT:
            raise NotDemoEnvironment(
                f"capital-gateway reports environment {environment!r}, not "
                f"{DEMO_ENVIRONMENT!r} — this module never touches a live account."
            )

    async def get(self, path: str, params: dict | None = None) -> dict:
        """A read. Retried once on a `5xx` before this module gives up on it."""
        response = await self._send("GET", path, params=params)
        if response.status_code >= 500:
            response = await self._send("GET", path, params=params)
        return _parsed(response)

    async def write(self, method: str, path: str, json: dict | None = None) -> dict:
        """A request that changes the account. Sent exactly once — see the module
        docstring — whatever the gateway answers or fails to."""
        response = await self._send(method, path, json=json)
        return _parsed(response)

    async def _send(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = await self._http.request(method, path, **kwargs)
        except httpx.TimeoutException as err:
            raise GatewayUnavailable(
                f"the gateway did not respond to {method} {path} within "
                f"{self._timeout_seconds:g}s"
            ) from err
        except httpx.RequestError as err:
            raise GatewayUnavailable(f"the gateway is unreachable: {err}") from err

        return response


def _parsed(response: httpx.Response) -> dict:
    if response.is_error:
        raise GatewayRefused(response.status_code, detail(response, upstream="capital-gateway"))
    return response.json()
