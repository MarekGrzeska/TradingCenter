"""An Entra access token, checked: signature against the tenant's published keys, issuer, audience and lifetime.
What Easy Auth did before the request reached the application, done where the application can be tested."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

import httpx
import jwt

log = logging.getLogger(__name__)

# Entra signs with RS256 and nothing else is accepted: a token naming `none` or an HMAC (keyed with the public
# key) is the classic way past a verifier that trusts the header.
ALGORITHMS = ["RS256"]

JWKS_URL = "https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys"

# Which application a token was issued to: `azp` in a v2 token, `appid` in a v1 one. Not `oid` or `sub`, which
# name the person — the records here are written in applications.
APPLICATION_CLAIMS = ("azp", "appid")

# A key set is re-read at most this often when a token names a `kid` we do not hold, so a stream of garbage
# `kid`s costs one fetch a minute and not one per request.
MIN_REFRESH_INTERVAL = 60.0
KEY_LIFETIME = 6 * 60 * 60.0


class InvalidToken(Exception):
    """The token is not one this process will believe. The message is for the log, never for the caller."""


KeyFetcher = Callable[[], Awaitable[dict[str, Any]]]


def _issuers(tenant_id: str) -> list[str]:
    # A v1 token (the API's `accessTokenAcceptedVersion` unset) and a v2 one name different issuers for one tenant.
    return [f"https://sts.windows.net/{tenant_id}/", f"https://login.microsoftonline.com/{tenant_id}/v2.0"]


class TokenVerifier:
    def __init__(
        self,
        *,
        tenant_id: str,
        audiences: Sequence[str],
        fetch_keys: KeyFetcher | None = None,
        leeway_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not tenant_id.strip():
            raise ValueError("a tenant id is required to verify a token")
        if not [a for a in audiences if a.strip()]:
            raise ValueError("at least one audience is required to verify a token")
        self._issuers = _issuers(tenant_id.strip())
        self._audiences = [a.strip() for a in audiences if a.strip()]
        self._leeway = leeway_seconds
        self._fetch_keys = fetch_keys or self._fetch_from_tenant(tenant_id.strip())
        self._clock = clock
        self._keys: dict[str, Any] = {}
        self._fetched_at: float | None = None
        self._last_attempt: float | None = None
        self._lock = asyncio.Lock()

    @staticmethod
    def _fetch_from_tenant(tenant_id: str) -> KeyFetcher:
        async def fetch() -> dict[str, Any]:
            async with httpx.AsyncClient(timeout=10.0) as http:
                response = await http.get(JWKS_URL.format(tenant=tenant_id))
                response.raise_for_status()
                return response.json()

        return fetch

    async def verify(self, token: str) -> dict[str, Any]:
        """The token's claims, or `InvalidToken`. Nothing in the token is read before the signature is."""
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as err:
            raise InvalidToken(f"not a token: {err}") from err
        if header.get("alg") not in ALGORITHMS:
            raise InvalidToken(f"algorithm {header.get('alg')!r} is not accepted")
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise InvalidToken("the token names no signing key")

        key = await self._key_for(kid)
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=ALGORITHMS,
                audience=self._audiences,
                issuer=self._issuers,
                leeway=self._leeway,
                options={"require": ["exp", "iss", "aud"]},
            )
        except jwt.PyJWTError as err:
            raise InvalidToken(f"{type(err).__name__}: {err}") from err
        return claims

    async def _key_for(self, kid: str) -> Any:
        key = self._keys.get(kid)
        if key is not None and not self._expired():
            return key
        async with self._lock:
            # Another request may have refreshed while this one waited for the lock.
            key = self._keys.get(kid)
            if key is not None and not self._expired():
                return key
            if self._may_refresh():
                await self._refresh()
            key = self._keys.get(kid)
        if key is None:
            raise InvalidToken(f"signing key {kid!r} is not one the tenant publishes")
        return key

    def _expired(self) -> bool:
        return self._fetched_at is None or self._clock() - self._fetched_at > KEY_LIFETIME

    def _may_refresh(self) -> bool:
        return self._last_attempt is None or self._clock() - self._last_attempt >= MIN_REFRESH_INTERVAL

    async def _refresh(self) -> None:
        self._last_attempt = self._clock()
        try:
            document = await self._fetch_keys()
        except Exception as err:  # noqa: BLE001 - the network, a non-2xx, malformed JSON: all mean "no new keys now"
            # The keys already held stay usable: a tenant endpoint that blinks must not lock the operator out.
            log.warning("the tenant's signing keys could not be fetched: %s", err)
            return
        keys: dict[str, Any] = {}
        for jwk in document.get("keys", []):
            if isinstance(jwk, dict) and jwk.get("kid") and jwk.get("kty") == "RSA":
                keys[jwk["kid"]] = jwt.PyJWK(jwk).key
        self._keys = keys
        self._fetched_at = self._clock()


def application_of(claims: dict[str, Any]) -> str | None:
    for name in APPLICATION_CLAIMS:
        value = claims.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
