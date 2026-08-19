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

from typing import Any

import httpx

from ..errors import GatewayRefused, GatewayUnreachable, UnreadablePayload

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


def http_client(api_key: str, timeout: httpx.Timeout = DEFAULT_TIMEOUT) -> httpx.AsyncClient:
    """A client sized for deep reads, presenting this module's caller key on every
    request. Owned by the caller, so a fill and an interactive request can share one
    connection pool — and one set of default headers — rather than opening one each."""
    return httpx.AsyncClient(timeout=timeout, headers={GATEWAY_KEY_HEADER: api_key})


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
