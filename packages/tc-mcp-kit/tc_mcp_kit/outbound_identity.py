"""The token this module presents when it calls another one. The inbound half is `network_identity`;
this is the same boundary from the other side, and it lived as seven identical copies in six modules.

Two behaviours, because the copies had two and the difference is real rather than accidental: a
caller that also holds a shared key logs the failure and sends the request anyway, letting the
upstream refuse it in a shape somebody reads; a caller with nothing else to present lets the error
out, because a failure at the door beats a 401 arriving as an unexplained tool result.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

import httpx
from azure.core.exceptions import AzureError
from azure.identity.aio import DefaultAzureCredential

log = logging.getLogger(__name__)


class ManagedIdentityAuth(httpx.Auth):
    """A bearer token on every request, from this module's own identity. Per request, not per
    connection: one read at start-up expires under a long process, and the streamable-http transport
    fixes its headers when the connection opens, so a session outliving its token fails for no
    readable reason."""

    def __init__(
        self,
        credential: DefaultAzureCredential,
        scope: str,
        *,
        send_without_token: str | None = None,
    ) -> None:
        """`send_without_token` is what the log line says will happen next when no token can be had
        — the caller's own words, because only the caller knows whether a key still goes with it.
        Left at `None`, the `AzureError` is not caught at all."""
        self._credential = credential
        self._scope = scope
        self._send_without_token = send_without_token

    async def async_auth_flow(
        self, request: httpx.Request
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
        if self._send_without_token is None:
            token = await self._credential.get_token(self._scope)
            request.headers["Authorization"] = f"Bearer {token.token}"
            yield request
            return

        try:
            token = await self._credential.get_token(self._scope)
        # Every way this fails is an `AzureError`: no identity on the host, a directory that will
        # not issue for this audience, a metadata endpoint not answering. All mean no token now.
        except AzureError as err:
            log.warning("no token for %s, %s: %s", self._scope, self._send_without_token, err)
        else:
            request.headers["Authorization"] = f"Bearer {token.token}"
        yield request
