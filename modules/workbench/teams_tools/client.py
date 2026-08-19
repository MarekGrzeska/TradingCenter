"""The seam every call to the teams surface passes through.

**No network.** The routes this speaks to are in the same process, reached through
`httpx.ASGITransport` — so what used to be two hops from the model to the catalogue is
none. HTTP is kept as the shape of the call rather than replaced by direct calls into
`teams.store`, and that is a decision with a reason
(`agent-and-teams-one-workbench/design.md`, D3): the owner filter, the revision
validation, the daily cost limit and the tool-catalogue check all live in the routers, and
a tool reaching past them would be a second copy of the access policy.

Every request carries the **operator's principal** in the header a platform authenticator
would have written. That is the whole mechanism by which a team created from the chat
belongs to the person who asked for it — and the principal is not invented here: it comes
off the incoming chat request, which the authenticator in front of this process has
already validated (`operator.py`).

Three outcomes, not two (`errors.py`). And one rule with teeth: **a write is never
retried.** A repeated `create_team` is a second team, a repeated `run_team` a second bill.
Reads may be retried once, because reading twice reads the same thing.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from starlette.types import ASGIApp
from tc_mcp_kit.detail import detail
from tc_runtime.auth import PRINCIPAL_ID_HEADER

from .errors import ToolRefusal, UpstreamUnavailable

log = logging.getLogger(__name__)

# Methods that change something on the other side. Everything here is decided by the
# method rather than by the path, so a route added later cannot fall into the retrying
# branch by being unrecognised.
_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


# Never resolved and never dialled — `ASGITransport` answers every request whatever the
# authority says. It exists because httpx requires an absolute URL, and it is spelled so a
# stray log line says which client produced it.
BASE_URL = "http://workbench.internal"


class TeamsClient:
    def __init__(self, app: ASGIApp, *, operator_identity_optional: bool) -> None:
        # `raise_app_exceptions=False` so a 500 from a route arrives here as a response
        # rather than as that route's exception unwinding into the model's turn — the whole
        # of `_read` below exists to turn a status into a sentence, and it cannot do that
        # for an exception that never became one.
        self._http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url=BASE_URL,
        )
        # Behind a property because it is the switch that decides whether a call may go out
        # with no identity: it is derived from settings validated at startup, and a plain
        # attribute would let anything holding the client widen that afterwards.
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

        # One retry, reads only. A 5xx on a write is left as it fell: the route may have
        # done the thing and failed on the way back, and asking again would be a second
        # team or a second run rather than a second attempt at the first.
        if response.status_code >= 500 and not is_write:
            response = await self._send(method, path, token=token, **kwargs)

        return self._read(response, method=method, path=path, is_write=is_write)

    async def _send(self, method: str, path: str, *, token: str | None, **kwargs) -> httpx.Response:
        # The operator's principal, in the header a platform authenticator writes. `None`
        # means the local shape, where nobody could have been authenticated: then the
        # header is **left off** rather than sent empty or invented, and the routes assign
        # the same principal they assign the local terminal.
        #
        # Nothing has to strip a caller-supplied copy of this header, because nothing comes
        # in: this client speaks to an application object, not to a socket. Whatever a
        # browser sent is gone before then — Easy Auth overwrites it in front of the
        # process.
        headers = {**kwargs.pop("headers", {})}
        if token is not None:
            headers[PRINCIPAL_ID_HEADER] = token
        try:
            return await self._http.request(method, path, headers=headers, **kwargs)
        except httpx.HTTPError as err:
            raise UpstreamUnavailable(f"the teams surface could not be reached: {err}") from err

    def _read(self, response: httpx.Response, *, method: str, path: str, is_write: bool) -> Any:
        if response.status_code == 401:
            # The operator's token, not this module's — and the difference matters to
            # whoever reads this sentence, because only one of them can be renewed by
            # signing in again.
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
