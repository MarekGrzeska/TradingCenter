"""The door to Telegram as this package reaches it: the gateway's own application, in this process. Only what a rule needs
to know is read here; sending arrives with delivery."""

from __future__ import annotations

from dataclasses import dataclass

import httpx


class GatewayUnreachable(Exception):
    """The door did not answer at all."""


@dataclass(frozen=True)
class Sent:
    """What the door said about one message. `transient` is the door's own word for 'ask again': a rate limit, Telegram
    out of reach, a busy gateway. Anything else that is not ok is an answer, and asking again gets the same one."""

    ok: bool
    transient: bool = False
    retry_after_seconds: int | None = None
    reason: str | None = None


@dataclass(frozen=True)
class Recipient:
    name: str
    bot: str
    receives: bool


class Gateway:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def recipients(self) -> list[Recipient]:
        """Everyone the door can write to, ready or not: a rule may be written for a recipient who has not tapped yet."""
        try:
            response = await self._client.get("/destinations")
        except httpx.RequestError as err:
            raise GatewayUnreachable(f"the door to Telegram did not answer: {err}") from err
        if response.is_error:
            raise GatewayUnreachable(f"the door to Telegram refused the list of recipients: HTTP {response.status_code}")
        return [Recipient(one["name"], one["bot"], bool(one["receives"])) for one in response.json()]

    async def send(self, destination: str, text: str) -> Sent:
        """One message to one recipient, now. Never raises for what the door answers — the answer is the result."""
        try:
            response = await self._client.post("/messages", json={"destination": destination, "text": text})
        except httpx.RequestError as err:
            return Sent(ok=False, transient=True, reason=f"the door to Telegram did not answer: {err}")
        if not response.is_error:
            return Sent(ok=True)
        detail, retryable, wait = _problem(response)
        transient = response.status_code in (429, 503) or retryable
        return Sent(ok=False, transient=transient, retry_after_seconds=wait, reason=detail)


def _problem(response: httpx.Response) -> tuple[str, bool, int | None]:
    """The door's own words for a refusal, and the two facts a caller decides by."""
    try:
        body = response.json()
    except ValueError:
        return (response.text.strip() or response.reason_phrase, False, None)
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, dict):
        wait = detail.get("retry_after_seconds")
        return (str(detail.get("detail") or detail), bool(detail.get("retryable")), wait if isinstance(wait, int) else None)
    return (str(detail or body), False, None)

