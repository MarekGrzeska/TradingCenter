"""The seam every call to the teams surface passes through — and no network: the routes are in the same
process, reached through `httpx.ASGITransport`. HTTP is kept as the shape of the call rather than replaced
by direct calls into the store, because the owner filter and every check live in the routers.

Every request carries the operator's principal in the header a platform authenticator would have written,
which is how a team created from the chat belongs to the person who asked. And one rule with teeth: a write
is never retried — a repeated `create_team` is a second team."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from starlette.types import ASGIApp
from tc_mcp_kit.detail import detail
from tc_runtime.auth import PRINCIPAL_ID_HEADER

from .errors import ToolRefusal, UpstreamUnavailable

log = logging.getLogger(__name__)

# Methods that change something on the other side. Decided by the method rather than by the path, so a
# route added later cannot fall into the retrying branch by being unrecognised.
_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


# Never resolved and never dialled — `ASGITransport` answers whatever the authority says. It exists because
# httpx requires an absolute URL, and it is spelled so a stray log line says which client produced it.
BASE_URL = "http://workbench.internal"


class TeamsClient:
    def __init__(self, app: ASGIApp, *, operator_identity_optional: bool) -> None:
        # `raise_app_exceptions=False` so a 500 arrives here as a response rather than as that route's
        # exception unwinding into the model's turn: `_read` turns a status into a sentence.
        self._http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url=BASE_URL,
        )
        # Behind a property because it is the switch that decides whether a call may go out with no
        # identity: a plain attribute would let anything holding the client widen that afterwards.
        self._operator_identity_optional = operator_identity_optional

    @property
    def operator_identity_optional(self) -> bool:
        return self._operator_identity_optional

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get(self, path: str, *, token: str | None, params: dict | None = None) -> Any:
        return await self._request("GET", path, token=token, params=params)

    async def post(self, path: str, *, token: str | None, json: dict | None = None) -> Any:
        return await self._request("POST", path, token=token, json=json)

    async def put(self, path: str, *, token: str | None, json: dict | None = None) -> Any:
        return await self._request("PUT", path, token=token, json=json)

    async def delete(self, path: str, *, token: str | None) -> Any:
        """`None` on success — `teams` answers `204`, and `_read` turns an empty body into
        exactly that. A caller with nothing to read is the point of the verb."""
        return await self._request("DELETE", path, token=token)

    async def _request(self, method: str, path: str, *, token: str | None, **kwargs) -> Any:
        is_write = method in _WRITE_METHODS
        response = await self._send(method, path, token=token, **kwargs)

        # One retry, reads only. A 5xx on a write is left as it fell: the route may have done the thing
        # and failed on the way back, and asking again would be a second team rather than a second attempt.
        if response.status_code >= 500 and not is_write:
            response = await self._send(method, path, token=token, **kwargs)

        return self._read(response, method=method, path=path, is_write=is_write)

    async def _send(self, method: str, path: str, *, token: str | None, **kwargs) -> httpx.Response:
        # The operator's principal, in the header a platform authenticator writes. `None` means the local
        # shape: the header is left off rather than sent empty, and the routes assign the local principal.
        headers = {**kwargs.pop("headers", {})}
        if token is not None:
            headers[PRINCIPAL_ID_HEADER] = token
        try:
            return await self._http.request(method, path, headers=headers, **kwargs)
        except httpx.HTTPError as err:
            raise UpstreamUnavailable(f"the teams surface could not be reached: {err}") from err

    def _read(self, response: httpx.Response, *, method: str, path: str, is_write: bool) -> Any:
        if response.status_code == 401:
            # The operator's token, not this module's — and the difference matters to whoever reads the
            # sentence, because only one of them can be renewed by signing in again.
            raise UpstreamUnavailable(
                "the teams surface did not accept the operator's identity. Nothing was "
                "read or written. Signing in again in the terminal renews it."
            )
        if response.status_code == 403:
            raise ToolRefusal(
                "the teams surface refused this operator's identity for that request. "
                "Nothing was read or written."
            )
        if response.status_code == 404:
            raise ToolRefusal(
                f"the teams catalogue has nothing at {path} for this operator. A team "
                "belonging to somebody else answers exactly like one that does not exist, "
                "so this is both answers at once."
            )
        if 400 <= response.status_code < 500:
            # teams writes its refusals for a reader who can act on them, so its own
            # words travel rather than a summary of them.
            raise ToolRefusal(detail(response, upstream="teams"))
        if response.status_code >= 500:
            raise UpstreamUnavailable(
                f"the teams surface answered {response.status_code} to {method} {path}. "
                + (
                    "Whether it took effect is unknown — read the catalogue before "
                    "trying again."
                    if is_write
                    else "Nothing was read."
                )
            )

        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as err:
            raise UpstreamUnavailable(
                f"the teams surface answered {method} {path} with something not JSON"
            ) from err
