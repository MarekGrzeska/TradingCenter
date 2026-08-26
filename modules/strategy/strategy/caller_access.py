"""Which caller may reach which surface, which Easy Auth cannot express: it authorizes an application, not a route.
The identity is the calling application read from the token's claims, never the header that names the person."""

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

# The token claim naming the application the token was issued to: `azp` in v2, `appid` in v1, and Easy
# Auth's long URI form. Deliberately not `oid` or `sub`: those name the person.
APPLICATION_CLAIMS = (
    "azp",
    "appid",
    "http://schemas.microsoft.com/identity/claims/appid",
)

UNAUTHENTICATED = "anonymous"


def calling_application(headers: dict[bytes, bytes]) -> str | None:
    """The application identifier this request was issued to, or `None`. `None` is a refusal, never a
    pass: it is exactly the request this record has nothing to say about."""
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


# `/ping` answers a constant. It reads nothing, so its answer cannot vary with anything this module
# holds. The test on this set asserts equality, so any addition here fails CI.
OPEN_PATHS = frozenset({"/ping"})

TOOLS_PREFIX = "/mcp"

# Every REST path this module publishes, written out rather than read off `app.routes`: a record derived
# from the application can never disagree with it, and disagreeing is the whole job.
REST_PATHS: tuple[str, ...] = (
    "/",
    "/health",
    "/strategies",
    "/strategies/{strategy_id}",
    # The configurator's four. Written rules are the operator's, like every other write
    # here — the workbench reads what a strategy decided and has no business composing one.
    "/definitions",
    "/definitions/{strategy_id}",
    "/definitions/{strategy_id}/revisions",
    "/definitions/{strategy_id}/revisions/{version}",
    "/parameter-sets",
    "/watches",
    "/watches/{watch_id}",
    "/decisions",
    "/decisions/{decision_id}",
    "/backtests",
    "/backtests/{run_id}",
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
    """The record, applied in front of the whole application. Holds `app.state` rather than a `Settings`:
    this is built while `create_app()` runs, and the lifespan fills the state later."""

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
            # The lifespan puts them there before anything serves, so a running process does not
            # reach this. "The settings were missing" must never be the reading that allows all.
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
            # Local work: nothing stands in front, so there is no identity to have. Logged rather
            # than silent — a deployed instance printing this is a misconfiguration to see.
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
