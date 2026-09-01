"""Telling the operator about a post worth waking them for.

Two rules shape this file, and both come from the gateway keeping no history of what it sent. The
marker is written **after** a success, never before — so a failed delivery leaves the post waiting
and the next collection pass tries again, which is the whole retry mechanism this system has. And a
post with no reading is never announced: an absent score is not a low one, and "just in case" would
turn the threshold into its opposite exactly where this module knows least.

The price is named rather than hidden: a delivery that succeeded and whose marker did not get
written announces the post a second time. A repeated notification is cheaper than a lost one, and
the other choice would need the gateway to remember messages.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import httpx
from azure.core.exceptions import AzureError
from azure.identity.aio import DefaultAzureCredential

from . import store
from .models import Post

log = logging.getLogger(__name__)

# Connect stays short: a gateway that is not listening should be reported now. Read is generous
# because the request is a message on its way to Telegram, not a database read.
DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=35.0, write=10.0, pool=5.0)

# How many posts one pass may announce. A day that produces forty alerts is a day the operator
# stops reading them, and the rest are still there on the next pass.
BATCH_LIMIT = 10

# Telegram's own ceiling is 4096 and the gateway refuses rather than truncating, so the excerpt is
# cut here — where the cut can be marked as one.
EXCERPT_CHARS = 900


class GatewayRefused(Exception):
    """The gateway answered, and the answer was a refusal — an unknown destination, a rate limit,
    a recipient who blocked the bot. Never read as "delivered"."""


class GatewayUnreachable(Exception):
    """The gateway did not answer at all."""


class _ManagedIdentityAuth(httpx.Auth):
    """A bearer token on every request, from this module's own identity — per request, because one
    fetched at start-up expires. The same shape `strategy` presents to the archive."""

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
    """A client for the gateway, presenting this module's identity where it has one. Left out —
    local work, and every test — nothing is presented, which the gateway supports on loopback."""
    auth = _ManagedIdentityAuth(DefaultAzureCredential(), scope) if scope else None
    return httpx.AsyncClient(timeout=timeout, auth=auth)


class Gateway:
    """The one route this module calls on telegram-gateway. It does not read the gateway's other
    routes: creating a bot and binding a destination are the operator's, through their own screen."""

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
    """The gateway's own words, kept whole — they carry the wait on a rate limit and the reason on
    a block, which is what makes this log worth reading."""
    try:
        body = response.json()
    except ValueError:
        return response.text.strip() or response.reason_phrase
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, dict):
        return str(detail.get("detail") or detail)
    return str(detail or body)


def message(post: Post) -> str:
    """One post as the operator reads it on a phone: what it scored, who wrote it, and enough of it
    to decide whether to open the terminal."""
    text = " ".join(post.content.split())
    if len(text) > EXCERPT_CHARS:
        text = text[:EXCERPT_CHARS].rstrip() + "…"
    lines = [
        f"Impact {post.impact_score}/10 — {post.author}",
        "",
        text,
    ]
    if post.topics:
        lines += ["", ", ".join(post.topics)]
    if post.url:
        lines += ["", post.url]
    return "\n".join(lines)


class Alerts:
    """The pass that says what is worth saying. Runs after enrichment in the same round, because a
    post is only a candidate once a model has read it."""

    def __init__(
        self,
        pool,
        gateway: Gateway,
        *,
        destination: str,
        min_score: int,
        batch_limit: int = BATCH_LIMIT,
    ) -> None:
        self._pool = pool
        self._gateway = gateway
        self._destination = destination
        self._min_score = min_score
        self._limit = batch_limit

    async def run(self, since: datetime) -> int:
        """How many posts were announced this pass. One failure costs that post only — and costs it
        nothing permanent, because the post keeps no marker and comes back next round."""
        async with self._pool.acquire() as conn:
            waiting = await store.posts_awaiting_notification(
                conn, since=since, min_score=self._min_score, limit=self._limit
            )
        sent = 0
        for post in waiting:
            try:
                await self._gateway.send(destination=self._destination, text=message(post))
            except (GatewayRefused, GatewayUnreachable) as err:
                # No marker, so the next pass tries again. Named at warning rather than swallowed:
                # a gateway refusing everything is a silence the operator has to be able to find.
                log.warning("could not announce post %s: %s", post.id, err)
                continue
            async with self._pool.acquire() as conn:
                await store.mark_notified(conn, post.id, at=datetime.now(UTC))
            sent += 1
        return sent


def build(pool, settings) -> Alerts | None:
    """The alerting this deployment is configured for, or `None`.

    `None` is a supported state, and the reason it is a return value rather than a refusal is the
    one `enrichment.build` gives: without a gateway the module collects and reads normally and says
    nothing, which `/state` reports rather than leaving anybody to guess at.
    """
    if not settings.alerts_configured:
        log.info("no telegram gateway is configured — posts will be collected and nobody told")
        return None
    return Alerts(
        pool,
        Gateway(
            settings.telegram_gateway_url,
            http_client(settings.telegram_gateway_scope),
        ),
        destination=settings.alert_destination,
        min_score=settings.alert_min_impact_score,
    )
