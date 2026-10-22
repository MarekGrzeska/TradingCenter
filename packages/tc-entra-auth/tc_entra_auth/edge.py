"""The door, in the process. A request that came through the edge proxy proves itself with an Entra token; one that
did not came from another service on the internal network and proves itself with the shared key. Whatever
passes leaves with one identity the module's own caller records already know how to read — the same
`X-MS-CLIENT-PRINCIPAL` that Easy Auth used to write — and whatever the client sent under that name is gone first.

Raw ASGI, outermost: it must see the request before any record does, and a streaming transport sits behind it."""

from __future__ import annotations

import base64
import hmac
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .roles import INTERNAL_ROLE, ROLES_HEADER, RolePolicy, roles_header_value
from .verifier import InvalidToken, TokenVerifier, application_of

log = logging.getLogger(__name__)

# The marker the proxy writes on every request it forwards, overwriting what came in. The internal network
# cannot carry it, so its absence means "from another service" — see `vps-edge`.
EDGE_HEADER = b"x-tc-edge"

# What the records read, and so what this writes. `-ID` and `-NAME` name the person for a delegated token.
PRINCIPAL_HEADER = b"x-ms-client-principal"
PRINCIPAL_ID_HEADER = b"x-ms-client-principal-id"
PRINCIPAL_NAME_HEADER = b"x-ms-client-principal-name"

DEFAULT_KEY_HEADER = b"x-gateway-key"
DEFAULT_INTERNAL_APPLICATION = "tc-internal"


def principal_blob(application: str) -> bytes:
    """The platform header's body, with the one claim the records read."""
    document = {"auth_typ": "aad", "claims": [{"typ": "azp", "val": application}]}
    return base64.b64encode(json.dumps(document).encode())


@dataclass(frozen=True)
class EdgeConfig:
    """What the door needs to know. `exempt_paths` are the ones that need no proof at all (a health probe, a handshake
    with its own one-time ticket) — what `excluded_paths` was. `key_paths` are the ones whose handler checks the shared
    key itself, reached from either side. A `verifier` of `None` is a process nothing external may reach: every
    request carrying the edge marker is refused."""

    verifier: TokenVerifier | None
    service_key: str | None
    internal_application_id: str = DEFAULT_INTERNAL_APPLICATION
    key_header: bytes = DEFAULT_KEY_HEADER
    exempt_paths: frozenset[str] = frozenset()
    key_paths: frozenset[str] = frozenset()
    # What a person's role may reach. `None` is a process with no roles (the gateway before this existed, a test): the
    # token or key is the whole credential, as before.
    role_policy: RolePolicy | None = None


# Returns the config once the process has read its settings, `None` when it is not a server (local work, or Azure
# with a platform authenticator in front) and raises `LookupError` before the settings exist: a request that arrives
# in that gap is refused, never waved through.
ConfigProvider = Callable[[], EdgeConfig | None]


class EdgeAuth:
    def __init__(self, app: ASGIApp, config: EdgeConfig | ConfigProvider | None) -> None:
        self._app = app
        self._config = config

    def _resolve(self) -> EdgeConfig | None:
        if callable(self._config):
            return self._config()
        return self._config

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self._app(scope, receive, send)
            return

        try:
            config = self._resolve()
        except LookupError:
            log.error("refused %s: the process has not read its settings yet", scope.get("path", ""))
            await _refuse(scope, receive, send, 503, "the module is still starting")
            return
        if config is None:
            await self._app(scope, receive, send)
            return

        raw: list[tuple[bytes, bytes]] = list(scope.get("headers", []))
        headers = {name.lower(): value for name, value in raw}
        # The roles header is the process's own to write, like the principal: whatever the client sent is gone.
        clean = [
            (n, v)
            for n, v in raw
            if not n.lower().startswith(PRINCIPAL_HEADER) and n.lower() != ROLES_HEADER
        ]
        path = scope.get("path", "")

        if path in config.exempt_paths or path in config.key_paths:
            await self._app({**scope, "headers": clean}, receive, send)
            return

        if EDGE_HEADER in headers:
            identity = await self._from_token(config, headers, path)
        else:
            identity = self._from_key(config, headers, path)
        if identity is None:
            await _refuse(scope, receive, send, 401, "not authenticated")
            return

        application, person, name, roles = identity
        policy = config.role_policy
        if policy is not None and not policy.allows(roles, scope.get("method", ""), path):
            log.warning("refused %s %s: roles %s have no access", scope.get("method", ""), path, sorted(roles))
            await _refuse(scope, receive, send, 403, "this person has no access")
            return
        clean.append((ROLES_HEADER, roles_header_value(roles)))
        clean.append((PRINCIPAL_HEADER, principal_blob(application)))
        clean.append((PRINCIPAL_ID_HEADER, person.encode()))
        clean.append((PRINCIPAL_NAME_HEADER, name.encode()))
        await self._app({**scope, "headers": clean}, receive, send)

    @staticmethod
    async def _from_token(
        config: EdgeConfig, headers: dict[bytes, bytes], path: str
    ) -> tuple[str, str, str, frozenset[str]] | None:
        authorization = headers.get(b"authorization", b"").decode("latin-1")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            log.warning("refused %s: the request came through the edge with no bearer token", path)
            return None
        if config.verifier is None:
            log.warning("refused %s: nothing external may reach this process", path)
            return None
        try:
            claims = await config.verifier.verify(token.strip())
        except InvalidToken as err:
            log.warning("refused %s: %s", path, err)
            return None
        application = application_of(claims)
        if application is None:
            log.warning("refused %s: the token names no application", path)
            return None
        person = _text(claims.get("oid")) or _text(claims.get("sub")) or application
        name = _text(claims.get("preferred_username")) or _text(claims.get("upn")) or person
        return application, person, name, _roles_of(claims)

    @staticmethod
    def _from_key(
        config: EdgeConfig, headers: dict[bytes, bytes], path: str
    ) -> tuple[str, str, str, frozenset[str]] | None:
        provided = headers.get(config.key_header.lower(), b"")
        expected = config.service_key.encode() if config.service_key else None
        # Compared as bytes: `compare_digest` raises on a non-ASCII `str`, and a garbage header must be a 401.
        if expected is None or not provided or not hmac.compare_digest(provided, expected):
            log.warning("refused %s: no valid service key on an internal request", path)
            return None
        internal = config.internal_application_id
        return internal, internal, internal, frozenset({INTERNAL_ROLE})


def _roles_of(claims: dict[str, Any]) -> frozenset[str]:
    """The token's `roles` claim, a list of app-role values. Anything else is no roles — never a reading that allows."""
    value = claims.get("roles")
    if not isinstance(value, list):
        return frozenset()
    return frozenset(item for item in value if isinstance(item, str))


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


async def _refuse(scope: Scope, receive: Receive, send: Send, status: int, detail: str) -> None:
    if scope["type"] == "websocket":
        # Closed before accept(): the client sees a refused handshake, not a feed that died.
        await send({"type": "websocket.close", "code": 1008, "reason": detail})
        return
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    response = JSONResponse({"detail": detail}, status_code=status, headers=headers)
    await response(scope, receive, send)
