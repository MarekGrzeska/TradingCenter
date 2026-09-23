"""Telegram's bot surface, and the one place a bot token is put on the wire.

**The token is part of the request path** (`/bot<token>/sendMessage`), which makes the URL itself a
credential. Nothing here logs a URL, and `_safe` is what every message about a failure goes through —
`telegram-gateway-upstream-access` makes that a requirement, because logging a failing request is the
most ordinary way to lose a secret.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from .errors import Blocked, RateLimited, TelegramRefused, TelegramUnreachable
from .redaction import redact

log = logging.getLogger(__name__)

# Long enough for `getUpdates` to hold a poll open, and the poll passes its own shorter deadline in
# the request, so this is the outer bound rather than the usual wait.
REQUEST_TIMEOUT_SECONDS = 65.0

# What Telegram says when the recipient has blocked the bot. Matched on the phrase because the status
# is a plain 403, which also covers a token that has been revoked — two different operator moves.
_BLOCKED_MARKERS = ("bot was blocked by the user", "user is deactivated", "bot can't initiate")


def _safe(token: str, text: str) -> str:
    """Every message about a failure passes through here on its way to a caller.

    Two substitutions, not one: the token this call is holding, and anything else of that shape —
    Telegram's own `description` sometimes echoes a URL, and it need not be this request's.
    """
    return redact(text.replace(token, "<token>") if token else text)


@dataclass(frozen=True, slots=True)
class Delivered:
    """What Telegram said about a message it accepted. Returned to the caller and kept nowhere."""

    message_id: int
    chat_id: int


class BotApi(Protocol):
    """What the rest of this module needs from Telegram's bot surface. A protocol so the tests get a
    fake rather than a network, and so the one real implementation stays replaceable."""

    async def send_message(self, token: str, *, chat_id: int, text: str) -> Delivered: ...

    async def get_me(self, token: str) -> dict[str, Any]: ...

    async def get_updates(self, token: str, *, offset: int, timeout: int) -> list[dict[str, Any]]: ...


class HttpBotApi:
    """The real one. One `httpx.AsyncClient` for every bot: the token is per request, not per client."""

    def __init__(self, client: httpx.AsyncClient, base_url: str) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")

    async def _call(self, token: str, method: str, payload: dict | None = None) -> Any:
        url = f"{self._base_url}/bot{token}/{method}"
        try:
            response = await self._client.post(url, json=payload or {})
        except httpx.HTTPError as err:
            # `str(err)` from httpx carries the URL, and the URL carries the token.
            raise TelegramUnreachable(_safe(token, f"{type(err).__name__}: {err}")) from err

        try:
            body = response.json()
        except ValueError as err:
            raise TelegramUnreachable(
                f"{response.status_code} with a body that is not JSON"
            ) from err

        if body.get("ok"):
            return body.get("result")

        description = _safe(token, str(body.get("description") or response.reason_phrase))
        parameters = body.get("parameters") or {}
        if "retry_after" in parameters:
            raise RateLimited(retry_after_seconds=int(parameters["retry_after"]))
        if response.status_code == 403 and any(
            marker in description.lower() for marker in _BLOCKED_MARKERS
        ):
            # The name is not known here — the send path knows which destination it was addressing,
            # and re-raises with it.
            raise Blocked(name="")
        raise TelegramRefused(description=description, status_code=response.status_code)

    async def send_message(self, token: str, *, chat_id: int, text: str) -> Delivered:
        result = await self._call(token, "sendMessage", {"chat_id": chat_id, "text": text})
        return Delivered(
            message_id=int(result["message_id"]), chat_id=int(result["chat"]["id"])
        )

    async def get_me(self, token: str) -> dict[str, Any]:
        """Who this token belongs to. How a pasted token becomes a bot row — its numeric id and its
        @name come from Telegram rather than from whoever typed them."""
        return await self._call(token, "getMe")

    async def get_updates(
        self, token: str, *, offset: int, timeout: int
    ) -> list[dict[str, Any]]:
        return await self._call(
            token,
            "getUpdates",
            {"offset": offset, "timeout": timeout, "allowed_updates": ["message"]},
        )


@asynccontextmanager
async def bot_api(base_url: str) -> AsyncIterator[BotApi]:
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        yield HttpBotApi(client, base_url)
