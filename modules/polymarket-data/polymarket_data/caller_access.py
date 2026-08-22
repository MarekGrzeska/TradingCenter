"""Which caller may reach which surface of this application.

The platform's own gate answers a narrower question than it looks like it does: Easy Auth
authorizes an **application**, and once a caller is through that door every path in this
process is behind it. This module serves two surfaces, so the record below is what Easy Auth
cannot express — route by route, which identity has business there.

**The boundary is not the same as `market-data`'s, and the difference is the whole point.**
There, the tool surface only reads, so the record keeps the tool callers away from every
route that writes. Here three tools write by design — they change the list of observations —
so what the record protects is different and smaller and harder: the tool caller must not
reach **deleting collected history**, which is the one act in this module nobody can undo,
and must not reach the rest of the REST contract either.

**The identity is the calling application, read from the token's own claims.** Not the
principal-id header, which for a delegated token names the person at the keyboard.

**A path not in the record is refused, not passed.** A REST route added next month would
otherwise be reachable by the workbench on the day it is written, and nothing would say so.

Raw ASGI, not `BaseHTTPMiddleware`, and that is load-bearing rather than stylistic:
`BaseHTTPMiddleware` buffers a response body in some Starlette versions, which would break
the streamable-http transport `/mcp` is served over.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import re
from enum import Enum

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

log = logging.getLogger(__name__)

PRINCIPAL_ID_HEADER = b"x-ms-client-principal-id"
PRINCIPAL_NAME_HEADER = b"x-ms-client-principal-name"
PRINCIPAL_HEADER = b"x-ms-client-principal"

# The token claim naming the application the token was issued to. `azp` in a v2 token,
# `appid` in a v1 one, and Easy Auth passes some claim types through as the long URI form.
# All three are the same fact: who is calling.
#
# Deliberately not `oid` or `sub`: those name the person, and this module admits programs.
# Measured elsewhere in this repository on 19 August 2026, by deploying the opposite
# assumption and refusing every request the terminal made.
APPLICATION_CLAIMS = (
    "azp",
    "appid",
    "http://schemas.microsoft.com/identity/claims/appid",
)

UNAUTHENTICATED = "anonymous"


def calling_application(headers: dict[bytes, bytes]) -> str | None:
    """The application identifier this request was issued to, or `None`.

    `None` is a refusal, never a pass: a request whose calling application cannot be read is
    exactly the request this record has nothing to say about.
    """
    raw = headers.get(PRINCIPAL_HEADER)
    if not raw:
        return None
    try:
        padded = raw + b"=" * (-len(raw) % 4)
        blob = json.loads(base64.b64decode(padded).decode("utf-8"))
    except (ValueError, binascii.Error):
        return None

    claims = blob.get("claims") or []
    for name in APPLICATION_CLAIMS:
        for claim in claims:
            if not isinstance(claim, dict):
                continue
            if claim.get("typ") == name and claim.get("val"):
                return str(claim["val"]).strip()
    return None


class Surface(str, Enum):
    TOOLS = "tools"
    REST = "rest"
    OPEN = "open"


# Reachable with no identity even where the requirement is on. Both are excluded from Easy
# Auth in production, which is exactly why they are named here rather than left to a prefix
# rule — and why the test on this set asserts equality, so any addition fails CI.
#
#   /       answers a constant naming this module, which is what the deploy probe reads to
#           tell this application from another one on the same plan.
#   /ping   answers a constant. It reads nothing, so its answer cannot vary with anything
#           the archive holds — that is what makes it exemptible at all.
OPEN_PATHS = frozenset({"/", "/ping"})

TOOLS_PREFIX = "/mcp"

# Every REST path this module publishes, as its route template. Written out rather than read
# off `app.routes`: a record derived from the application can never disagree with it, and
# disagreeing is the whole job — `test_caller_access.py` holds this list against the
# published document, so a new route fails a test until somebody decides which surface it
# belongs to.
REST_PATHS: tuple[str, ...] = (
    "/health",
    "/events",
    "/events/{provider_event_id}",
    "/events/{provider_event_id}/tracking",
    "/events/{provider_event_id}/history",
    "/events/{provider_event_id}/changes",
    "/events/{event_id}/group",
    "/groups",
    "/groups/{group_id}",
    "/outcomes/{outcome_id}/history",
    "/snapshot",
    # FastAPI's own, published by the framework rather than by a router. They describe the
    # REST contract, so they belong to the caller that consumes it.
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
    "/openapi.json",
)


def _as_pattern(template: str) -> re.Pattern[str]:
    parts = [re.escape(part) for part in re.split(r"\{[^}]+\}", template)]
    return re.compile("^" + "[^/]+".join(parts) + "$")


_REST_PATTERNS = tuple(_as_pattern(template) for template in REST_PATHS)


def surface_for(path: str) -> Surface | None:
    """Which surface this path belongs to, or `None` for a path the record does not name."""
    if path in OPEN_PATHS:
        return Surface.OPEN
    if path == TOOLS_PREFIX or path.startswith(f"{TOOLS_PREFIX}/"):
        return Surface.TOOLS
    normalized = path.rstrip("/") or "/"
    if normalized in OPEN_PATHS:
        return Surface.OPEN
    if any(pattern.match(path) or pattern.match(normalized) for pattern in _REST_PATTERNS):
        return Surface.REST
    return None


class CallerAccess:
    """The record, applied in front of the whole application."""

    def __init__(self, app: ASGIApp, state) -> None:
        self._app = app
        self._state = state

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self._app(scope, receive, send)
            return

        path = scope.get("path", "")
        surface = surface_for(path)

        if surface is None:
            log.warning("request refused: %s is not in the caller-access record", path)
            await self._refuse(scope, receive, send, 403, "this path is not open to any caller")
            return

        if surface is Surface.OPEN:
            await self._app(scope, receive, send)
            return

        settings = getattr(self._state, "settings", None)
        if settings is None:
            # The lifespan puts them there before anything serves, so a running process does
            # not reach this. Refused rather than passed anyway: "the settings were missing"
            # must never be the reading under which everything is allowed.
            log.error("request refused: settings are not on the application state yet")
            await self._refuse(scope, receive, send, 503, "the archive is still starting")
            return

        headers = dict(scope.get("headers", []))
        application = calling_application(headers)
        principal = (
            (headers.get(PRINCIPAL_ID_HEADER) or headers.get(PRINCIPAL_NAME_HEADER) or b"")
            .decode("utf-8", errors="replace")
            .strip()
        )

        if not settings.require_authenticated_principal:
            # Local work: nothing stands in front, so there is no identity to have and no
            # list to be on. Logged rather than passed silently — a deployed instance
            # printing this line is a misconfiguration somebody needs to see.
            log.info("request on %s from %s", path, application or principal or UNAUTHENTICATED)
            await self._app(scope, receive, send)
            return

        if application is None:
            log.warning(
                "request refused: the calling application cannot be named on %s (principal %s)",
                path,
                principal or UNAUTHENTICATED,
            )
            await self._refuse(scope, receive, send, 401, "not authenticated")
            return

        allowed = (
            settings.tool_caller_ids if surface is Surface.TOOLS else settings.rest_caller_ids
        )
        if application not in allowed:
            # The application, never the credential it arrived with, and never the request.
            log.warning(
                "request refused: application %s has no access to %s (%s)",
                application,
                path,
                surface,
            )
            await self._refuse(
                scope, receive, send, 403, f"this caller has no access to {surface.value}"
            )
            return

        log.info("request on %s from application %s (principal %s)", path, application, principal)
        await self._app(scope, receive, send)

    async def _refuse(
        self, scope: Scope, receive: Receive, send: Send, status: int, detail: str
    ) -> None:
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008, "reason": detail})
            return
        response = JSONResponse({"detail": detail}, status_code=status)
        await response(scope, receive, send)
