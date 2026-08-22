"""Which caller may reach which surface of this application.

The platform's own gate answers a narrower question than it looks like it does: Easy Auth
authorizes an **application**, and once a caller is through that door every path in this
process is behind it. This module serves two surfaces to two different callers — the
workbench reads `pending_setups` at `/mcp`, the operator reads and writes the REST
contract — so the record below is the thing Easy Auth cannot express: path by path, which
identity has business there.

**A path not in the record is refused, not passed.** The default matters more than any
single entry: a REST route added next month would otherwise be reachable by the workbench
on the day it is written, and nothing would say so.

**The identity is the calling application, read from the token's own claims** — never the
principal-id header, which for a delegated token names the person at the keyboard.
market-data learned that in production on 19 August 2026 by deploying the opposite
assumption and refusing every request the terminal made.

This is market-data's file with this module's paths: raw ASGI rather than
`BaseHTTPMiddleware`, which is load-bearing rather than stylistic — `BaseHTTPMiddleware`
buffers a response body in some Starlette versions, and that would break the
streamable-http transport `/mcp` is served over.
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
# Deliberately not `oid` or `sub`: those name the person, and this module admits programs.
APPLICATION_CLAIMS = (
    "azp",
    "appid",
    "http://schemas.microsoft.com/identity/claims/appid",
)

UNAUTHENTICATED = "anonymous"


def calling_application(headers: dict[bytes, bytes]) -> str | None:
    """The application identifier this request was issued to, or `None` if it cannot be named.

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


# `/ping` answers a constant. It reads nothing, so its answer cannot vary with anything
# this module holds — that is what makes it exemptible at all. The test on this set asserts
# equality rather than membership, so **any** addition here fails CI.
OPEN_PATHS = frozenset({"/ping"})

TOOLS_PREFIX = "/mcp"

# Every REST path this module publishes, as its route template. Written out rather than
# read off `app.routes`: a record derived from the application can never disagree with it,
# and disagreeing is the whole job. `tests/test_caller_access.py` holds this list against
# the published document, so a new route fails a test until somebody decides which surface
# it belongs to.
REST_PATHS: tuple[str, ...] = (
    "/",
    "/health",
    "/strategies",
    "/strategies/{strategy_id}",
    "/parameter-sets",
    "/watches",
    "/watches/{watch_id}",
    "/decisions",
    "/decisions/{decision_id}",
    # FastAPI's own, published by the framework rather than by a router. They describe the
    # REST contract, so they belong to the caller that consumes it.
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
    "/openapi.json",
)


def _as_pattern(template: str) -> re.Pattern[str]:
    """`/watches/{watch_id}` as a regex matching one path segment per placeholder."""
    parts = [re.escape(part) for part in re.split(r"\{[^}]+\}", template)]
    return re.compile("^" + "[^/]+".join(parts) + "$")


_REST_PATTERNS = tuple(_as_pattern(template) for template in REST_PATHS)


def surface_for(path: str) -> Surface | None:
    """Which surface this path belongs to, or `None` for a path the record does not name."""
    if path in OPEN_PATHS:
        return Surface.OPEN
    if path == TOOLS_PREFIX or path.startswith(f"{TOOLS_PREFIX}/"):
        return Surface.TOOLS
    # A trailing slash is the same route to Starlette's redirect and a different string
    # here; normalized so `/watches/` cannot read as a path nobody recorded.
    normalized = path.rstrip("/") or "/"
    if any(pattern.match(path) or pattern.match(normalized) for pattern in _REST_PATTERNS):
        return Surface.REST
    return None


class CallerAccess:
    """The record, applied in front of the whole application.

    Holds `app.state` rather than a `Settings`: this is built while `create_app()` runs and
    the settings are put on the state by the lifespan, long afterwards.
    """

    def __init__(self, app: ASGIApp, state) -> None:
        self._app = app
        self._state = state

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
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
            # The lifespan puts them there before anything serves, so this is not a state a
            # running process reaches. Refused rather than passed anyway: "the settings were
            # missing" must never be the reading under which everything is allowed.
            log.error("request refused: settings are not on the application state yet")
            await self._refuse(scope, receive, send, 503, "the platform is still starting")
            return

        headers = dict(scope.get("headers", []))
        application = calling_application(headers)
        # Who the request is *for*, kept for the log line only. A person and an application
        # are two different facts and only one of them is what this record is written in.
        principal = (
            (headers.get(PRINCIPAL_ID_HEADER) or headers.get(PRINCIPAL_NAME_HEADER) or b"")
            .decode("utf-8", errors="replace")
            .strip()
        )

        if not settings.require_authenticated_principal:
            # Local work: nothing stands in front, so there is no identity to have and no
            # list to be on. Logged as such rather than silently — a deployed instance
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
        """One refusal, in the shape `contract.Problem` publishes — a refused caller reads
        the same body here as it would from any route that turned it down."""
        response = JSONResponse({"detail": detail}, status_code=status)
        await response(scope, receive, send)
