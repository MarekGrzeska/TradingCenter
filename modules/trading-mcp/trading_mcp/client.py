"""The one seam every call to `capital-gateway` passes through, and the demo-only guard in front of
every write. Reads retry once on a 5xx; writes never — the gateway accepts no idempotency key."""

from __future__ import annotations

import logging

import httpx
from azure.identity.aio import DefaultAzureCredential
from tc_mcp_kit.detail import detail
from tc_mcp_kit.outbound_identity import ManagedIdentityAuth

from .config import Settings
from .errors import GatewayRefused, GatewayUnavailable, NotDemoEnvironment

# Matches `capital_gateway/config.py`'s `API_KEY_HEADER`. Duplicated rather than imported: no shared
# library between modules.
GATEWAY_KEY_HEADER = "X-Gateway-Key"

DEMO_ENVIRONMENT = "demo"

log = logging.getLogger(__name__)



class GatewayClient:
    def __init__(self, settings: Settings) -> None:
        scope = settings.capital_gateway_scope
        self._credential = DefaultAzureCredential() if scope else None
        self._http = httpx.AsyncClient(
            base_url=settings.capital_gateway_url,
            timeout=settings.capital_gateway_request_timeout_seconds,
            headers={GATEWAY_KEY_HEADER: settings.capital_gateway_api_key},
            auth=(
                ManagedIdentityAuth(self._credential, scope, send_without_token="sending the caller key alone")
                if self._credential is not None and scope
                else None
            ),
        )
        self._timeout_seconds = settings.capital_gateway_request_timeout_seconds

    async def aclose(self) -> None:
        await self._http.aclose()
        if self._credential is not None:
            await self._credential.close()

    async def ensure_demo_environment(self) -> None:
        """Refuse to proceed unless the gateway confirms it is bound to the demo account. Asked once,
        before the port opens, and not again: the re-check could only ever prove the gateway answered."""
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
