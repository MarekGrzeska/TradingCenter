"""One request to the gateway, and one reading of what came back: not listening, refused, or
unreadable. That three-way split was written out at six call sites before it moved here."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from azure.core.exceptions import AzureError
from azure.identity.aio import DefaultAzureCredential

from ..errors import GatewayRefused, GatewayUnreachable, UnreadablePayload

log = logging.getLogger(__name__)

# A deep read is tens of provider calls behind one HTTP request, so the read timeout is minutes.
# Connect stays short: a gateway that is not listening should be reported now, not in three minutes.
DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=300.0, write=10.0, pool=5.0)

# Matches capital-gateway's API_KEY_HEADER. Duplicated rather than imported: the two modules share
# no code, so a rename has to be a deliberate edit rather than a silent break through an import.
GATEWAY_KEY_HEADER = "X-Gateway-Key"


class _ManagedIdentityAuth(httpx.Auth):
    """A bearer token on every request, from this module's own identity. Per request, because one read
    at start-up expires under a long process; a token that cannot be had is logged and the key goes alone."""

    def __init__(self, credential: DefaultAzureCredential, scope: str) -> None:
        self._credential = credential
        self._scope = scope

    async def async_auth_flow(
        self, request: httpx.Request
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
        try:
            token = await self._credential.get_token(self._scope)
        # Every way this fails is an `AzureError`: no identity on the host, a directory that will
        # not issue for this audience, a metadata endpoint not answering. All mean no token now.
        except AzureError as err:
            log.warning(
                "no token for %s, sending the caller key alone: %s", self._scope, err
            )
        else:
            request.headers["Authorization"] = f"Bearer {token.token}"
        yield request


def http_client(
    api_key: str,
    scope: str | None = None,
    timeout: httpx.Timeout = DEFAULT_TIMEOUT,
) -> httpx.AsyncClient:
    """A client sized for deep reads, presenting this module's caller key on every request. `scope`
    names the gateway's audience where this module has an identity; without one the key is the whole credential."""
    auth = _ManagedIdentityAuth(DefaultAzureCredential(), scope) if scope else None
    return httpx.AsyncClient(
        timeout=timeout,
        headers={GATEWAY_KEY_HEADER: api_key},
        auth=auth,
    )


async def get_json(
    client: httpx.AsyncClient, url: str, *, params: dict[str, Any], what: str
) -> Any:
    """GET one gateway route and hand back its decoded body. `what` names the thing being asked for
    and goes into both failure sentences, so an operator reads which question went unanswered."""
    try:
        response = await client.get(url, params=params)
    except httpx.RequestError as err:
        raise GatewayUnreachable(f"the gateway did not answer for {what}: {err}") from err

    if response.is_error:
        raise GatewayRefused(response.status_code, _detail(response))

    try:
        return response.json()
    except ValueError as err:
        raise UnreadablePayload(f"the gateway's answer for {what} was not JSON: {err}") from err


def _detail(response: httpx.Response) -> str:
    """What the gateway said. Its error handler puts the cause in `detail`; anything
    else is a failure that never reached that handler, so the body is read raw."""
    try:
        body = response.json()
    except ValueError:
        return response.text.strip() or response.reason_phrase
    if isinstance(body, dict) and isinstance(body.get("detail"), str):
        return body["detail"]
    return str(body)
