"""Telling the operator that a strategy has found something.

Two rules, and both are about not becoming noise. **Only a decision that names a trade** — a refusal
is the ordinary outcome of most passes, and announcing it would bury the one that matters. And
**only when it is a change** from the last decision for that pair: the loop evaluates on every closed
bar, so one setup that stands for ten bars is ten identical decisions.

The marker is written after the gateway answered with a success, never before. A failed delivery
leaves the decision unmarked, and this is deliberate rather than incidental: the gateway remembers
nothing it sent, so the absence of this marker is the only retry there is.

The client below is this module's own, and duplicating `social_data.alerts` is the point: no module
imports another, and the shape they share is thirty lines of httpx that each owns for itself.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import httpx
from azure.core.exceptions import AzureError
from azure.identity.aio import DefaultAzureCredential

from .spec import Decision
from .store import RecordedDecision

log = logging.getLogger(__name__)

# Connect stays short: a gateway that is not listening should be reported now. Read is generous
# because the request is a message on its way to Telegram, not a database read.
DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=35.0, write=10.0, pool=5.0)


class GatewayRefused(Exception):
    """The gateway answered, and the answer was a refusal. Never read as "delivered"."""


class GatewayUnreachable(Exception):
    """The gateway did not answer at all."""


class _ManagedIdentityAuth(httpx.Auth):
    """A bearer token on every request, from this module's own identity — per request, because one
    fetched at start-up expires. The twin of what `archive.py` presents to market-data."""

    def __init__(self, credential: DefaultAzureCredential, scope: str) -> None:
        self._credential = credential
        self._scope = scope

    async def async_auth_flow(
        self, request: httpx.Request
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
        try:
            token = await self._credential.get_token(self._scope)
        except AzureError as err:
            log.warning("no token for %s; the gateway will refuse this request: %s", self._scope, err)
        else:
            request.headers["Authorization"] = f"Bearer {token.token}"
        yield request


def http_client(
    scope: str | None = None, timeout: httpx.Timeout = DEFAULT_TIMEOUT
) -> httpx.AsyncClient:
    """A client for the gateway, presenting this module's identity where it has one."""
    auth = _ManagedIdentityAuth(DefaultAzureCredential(), scope) if scope else None
    return httpx.AsyncClient(timeout=timeout, auth=auth)


class Gateway:
    """The one route this module calls on telegram-gateway. Sending is all it does there — this
    platform decides and never touches an account, and it does not manage the gateway either."""

    def __init__(self, base_url: str, client: httpx.AsyncClient) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client

    async def send(self, *, destination: str, text: str) -> None:
        try:
            response = await self._client.post(
                f"{self._base_url}/messages", json={"destination": destination, "text": text}
            )
        except httpx.RequestError as err:
            raise GatewayUnreachable(f"the gateway did not answer: {err}") from err
        if response.is_error:
            raise GatewayRefused(f"the gateway refused: {_detail(response)}")


def _detail(response: httpx.Response) -> str:
    """The gateway's own words, kept whole: they carry the wait on a rate limit and the reason on a
    block, which is the difference between a log worth reading and "it failed"."""
    try:
        body = response.json()
    except ValueError:
        return response.text.strip() or response.reason_phrase
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, dict):
        return str(detail.get("detail") or detail)
    return str(detail or body)


def is_new_setup(decision: Decision, previous: RecordedDecision | None) -> bool:
    """Whether this decision is worth saying out loud.

    A trade, and one the operator has not already been told about: the same direction standing from
    the previous bar is the same setup, not a second one. A direction that flipped is a new setup and
    says so — that is a position to reverse, not a repetition.
    """
    if decision.action != "trade":
        return False
    if previous is None or previous.decision.action != "trade":
        return True
    return previous.decision.direction != decision.direction


def message(strategy_id: str, symbol: str, decision: Decision) -> str:
    """One decision as the operator reads it on a phone. No instruction and no size: this platform
    decides, teams execute, and a message that read like an order would be claiming otherwise."""
    lines = [
        f"{symbol} — {decision.direction} ({strategy_id})",
        "",
        f"entry {decision.entry}  stop {decision.stop}  target {decision.target}",
    ]
    if decision.rr is not None:
        lines.append(f"reward/risk {decision.rr:.2f}")
    if decision.score is not None:
        lines.append(f"score {decision.score:g}")
    if decision.reason:
        lines += ["", decision.reason]
    return "\n".join(lines)


class Alerts:
    """What the loop calls when a pass has found something. Holds no state: what is already said is
    a column on the decision, not something this object remembers."""

    def __init__(self, gateway: Gateway, *, destination: str) -> None:
        self._gateway = gateway
        self._destination = destination

    async def announce(
        self, pool, *, strategy_id: str, symbol: str, decision: Decision, decision_id: int
    ) -> bool:
        """Sends, then marks — and answers whether it got that far.

        A refusal is logged and swallowed: the platform's job is to decide, and being unable to say
        so MUST NOT be a reason not to have decided. The decision stands, unmarked, and the next
        change announces itself.
        """
        from . import store  # local: `store` imports nothing of this, and this keeps it that way

        try:
            await self._gateway.send(
                destination=self._destination,
                text=message(strategy_id, symbol, decision),
            )
        except (GatewayRefused, GatewayUnreachable) as err:
            log.warning("could not announce %s on %s: %s", strategy_id, symbol, err)
            return False
        async with pool.acquire() as conn:
            await store.mark_decision_notified(conn, decision_id, at=datetime.now(UTC))
        return True


def build(settings) -> Alerts | None:
    """The alerting this deployment is configured for, or `None`.

    `None` is a supported state: without a gateway the platform evaluates and records exactly as it
    did, and says nothing. That is also the rollback — clear the address and restart.
    """
    if not settings.alerts_configured:
        log.info("no telegram gateway is configured — decisions will be recorded and nobody told")
        return None
    return Alerts(
        Gateway(settings.telegram_gateway_url, http_client(settings.telegram_gateway_scope)),
        destination=settings.alert_destination,
    )
