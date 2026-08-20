"""One request to the gateway, and one reading of what came back.

Every route this module calls fails in the same three ways, and each of them is a
different thing for a caller to do about it: the gateway is not listening
(`GatewayUnreachable`), it answered and said no (`GatewayRefused`), or it answered with
something this module cannot read (`UnreadablePayload`). That three-way split was written
out at six call sites across `history.py` and `instruments.py`, identical apart from the
phrase naming what was being asked for.

Kept private to the package: nothing outside `market_data.gateway` should be reaching the
gateway at all, which is what this package's own docstring says it is for.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from azure.core.exceptions import AzureError
from azure.identity.aio import DefaultAzureCredential

from ..errors import GatewayRefused, GatewayUnreachable, UnreadablePayload

log = logging.getLogger(__name__)

# A deep read is tens of provider calls behind one HTTP request, so the read timeout is
# minutes rather than seconds. Connect stays short: a gateway that is not listening
# should be reported as unreachable now, not after three minutes of waiting.
DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=300.0, write=10.0, pool=5.0)

# Matches capital-gateway's API_KEY_HEADER. Duplicated rather than imported — the two
# modules share no code, only the header name as a convention (architecture.md, "Why no
# shared library") — so a rename on one side has to be a deliberate edit on the other,
# not a silent break through a shared import. `stream.py` reuses this constant rather
# than defining its own copy, because within this module — unlike across modules — one
# name for the same header is simply not duplicating anything.
GATEWAY_KEY_HEADER = "X-Gateway-Key"


class _ManagedIdentityAuth(httpx.Auth):
    """A bearer token on every request, from this module's own identity.

    Per request rather than per client: a token read once at start-up would expire under a
    process that runs for days, and the failure would arrive mid-fill as a refusal that
    reads like the gateway having changed its mind. `DefaultAzureCredential` caches
    internally and only goes to the directory when the cached token is close to expiring,
    so the cost of asking every time is a dictionary lookup.

    The key travels alongside and is not replaced by this. Until the gateway's door is
    flipped to require authentication, the key is what gets these requests in; after it,
    the token is — and one deployment carrying both is what makes the two applies
    independent of the two deploys (`the-gateway-door-authenticates/design.md`).

    **A token that cannot be had does not stop the request.** It is logged and the request
    goes out on the key alone, which is deliberate and is the half of this that keeps the
    rollout ordered: between the deploy and the flip the key is still what opens the door,
    so a directory hiccup here would otherwise be an archive that stops filling for a
    credential nothing yet asks for. After the flip the gateway answers such a request
    `401` itself, and a refusal from the gateway is a refusal this module already reports
    as one.
    """

    def __init__(self, credential: DefaultAzureCredential, scope: str) -> None:
        self._credential = credential
        self._scope = scope

    async def async_auth_flow(
        self, request: httpx.Request
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
        try:
            token = await self._credential.get_token(self._scope)
        # Every way this fails is an `AzureError`: no identity on the host, a
        # directory that will not issue for this audience, or the metadata endpoint
        # not answering. All three mean the same thing here — no token this time.
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
    """A client sized for deep reads, presenting this module's caller key on every
    request. Owned by the caller, so a fill and an interactive request can share one
    connection pool — and one set of default headers — rather than opening one each.

    `scope` names the gateway's audience where this module has an identity to present.
    Left out — local work, and every test that does not care — the key is the whole
    credential, which is a supported configuration rather than a degraded one.
    """
    auth = _ManagedIdentityAuth(DefaultAzureCredential(), scope) if scope else None
    return httpx.AsyncClient(
        timeout=timeout,
        headers={GATEWAY_KEY_HEADER: api_key},
        auth=auth,
    )


async def get_json(
    client: httpx.AsyncClient, url: str, *, params: dict[str, Any], what: str
) -> Any:
    """GET one gateway route and hand back its decoded body.

    `what` names the thing being asked for and goes into both failure sentences, so an
    operator reads which question went unanswered rather than which URL did — "the
    gateway did not answer for US100 MINUTE" is the line worth logging.
    """
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
