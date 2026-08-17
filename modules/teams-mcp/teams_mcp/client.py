"""The client for `teams` — the one seam every call passes through, and so the one place
the two identities are kept apart.

Every request carries the **operator's** token as `Authorization`. That is the whole
mechanism by which a team created from the chat belongs to the person who asked for it:
the authenticator in front of `teams` validates that token and puts their principal on the
request, exactly as it does for the terminal (design.md, D2).

This module's *own* managed identity is a different credential answering a different
question, and it is not sent here at all — it proves `agent`'s right to reach *this*
module, one hop earlier. `teams_scope` exists for the day that changes; today the token
that opens `teams` is the operator's, and there is no path in this file that substitutes
one for the other.

Three outcomes, not two (`errors.py`). And one rule with teeth: **a write is never
retried.** A repeated `create_team` is a second team, a repeated `run_team` a second bill.
Reads may be retried once, because reading twice reads the same thing.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .config import Settings
from .errors import ToolRefusal, UpstreamUnavailable

log = logging.getLogger(__name__)

# Methods that change something on the other side. Everything here is decided by the
# method rather than by the path, so a route added later cannot fall into the retrying
# branch by being unrecognised.
_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class TeamsClient:
    def __init__(self, settings: Settings) -> None:
        self._http = httpx.AsyncClient(
            base_url=settings.teams_url,
            timeout=settings.teams_request_timeout_seconds,
        )
        self._timeout_seconds = settings.teams_request_timeout_seconds
        # Read here so the tool seam can ask without `tools.register` growing a `Settings`
        # parameter to carry one bool to where an object built from those settings already
        # stands (design.md, "Decyzja zostaje w operator.py, a warunek dojeżdża klientem").
        self.operator_identity_optional = settings.operator_identity_optional

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get(self, path: str, *, token: str | None, params: dict | None = None) -> Any:
        return await self._request("GET", path, token=token, params=params)

    async def post(self, path: str, *, token: str | None, json: dict | None = None) -> Any:
        return await self._request("POST", path, token=token, json=json)

    async def put(self, path: str, *, token: str | None, json: dict | None = None) -> Any:
        return await self._request("PUT", path, token=token, json=json)

    async def _request(self, method: str, path: str, *, token: str | None, **kwargs) -> Any:
        is_write = method in _WRITE_METHODS
        response = await self._send(method, path, token=token, **kwargs)

        # One retry, reads only (specs/teams-mcp-upstream-access, "Wołanie modułu
        # `teams` ma skończony czas"). A 5xx on a write is left as it fell: `teams` may
        # have done the thing and failed on the way back, and asking again would be a
        # second team or a second run rather than a second attempt at the first.
        if response.status_code >= 500 and not is_write:
            response = await self._send(method, path, token=token, **kwargs)

        return self._read(response, method=method, path=path, is_write=is_write)

    async def _send(self, method: str, path: str, *, token: str | None, **kwargs) -> httpx.Response:
        # The operator's token, not this module's. See this file's docstring. `None` means
        # the local shape, where nobody could have issued one: then the header is **left
        # off** rather than sent empty or invented — `teams` reads no `Authorization`
        # locally anyway, and a fabricated `Bearer` would start behaving differently the
        # day it did (design.md, "Brak nagłówka, nie udawany token").
        headers = {**kwargs.pop("headers", {})}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        try:
            return await self._http.request(method, path, headers=headers, **kwargs)
        except httpx.TimeoutException as err:
            raise UpstreamUnavailable(
                f"teams did not answer within {self._timeout_seconds:g}s. "
                + (
                    "This call may or may not have taken effect — read the catalogue "
                    "before trying it again."
                    if method in _WRITE_METHODS
                    else "Nothing was read; this says nothing about the catalogue."
                )
            ) from err
        except httpx.HTTPError as err:
            raise UpstreamUnavailable(f"teams could not be reached: {err}") from err

    def _read(self, response: httpx.Response, *, method: str, path: str, is_write: bool) -> Any:
        if response.status_code == 401:
            # The operator's token, not this module's — and the difference matters to
            # whoever reads this sentence, because only one of them can be renewed by
            # signing in again.
            raise UpstreamUnavailable(
                "teams did not accept the operator's credential — it has most likely "
                "expired. Nothing was read or written. Signing in again in the terminal "
                "renews it."
            )
        if response.status_code == 403:
            raise ToolRefusal(
                "teams refused this operator's credential for that request. Nothing was "
                "read or written."
            )
        if response.status_code == 404:
            raise ToolRefusal(
                f"teams has nothing at {path} for this operator. A team belonging to "
                "somebody else answers exactly like one that does not exist, so this is "
                "both answers at once."
            )
        if 400 <= response.status_code < 500:
            # teams writes its refusals for a reader who can act on them, so its own
            # words travel rather than a summary of them.
            raise ToolRefusal(_detail(response))
        if response.status_code >= 500:
            raise UpstreamUnavailable(
                f"teams answered {response.status_code} to {method} {path}. "
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
                f"teams answered {method} {path} with something that is not JSON"
            ) from err


def _detail(response: httpx.Response) -> str:
    """FastAPI spells a refusal two ways — a `detail` string, or its own list of
    validation objects. Both are teams' own words and both travel unedited."""
    try:
        body = response.json()
    except ValueError:
        return response.text.strip() or f"teams refused with HTTP {response.status_code}"

    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list):
        parts = [
            str(entry.get("msg", entry)) if isinstance(entry, dict) else str(entry)
            for entry in detail
        ]
        return "; ".join(parts)
    return response.text.strip() or f"teams refused with HTTP {response.status_code}"
