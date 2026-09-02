"""Which caller may reach which surface — the machinery, not the record. Easy Auth authorizes an
application and not a route, so a module that serves two surfaces from one process has to say the
rest itself. What each module says stays in its own `caller_access.py`: the paths, the prefix, and
the reason. Only this, which was identical to within a comment in five of them, lives here."""

from __future__ import annotations

import base64
import binascii
import json
import logging
import re
from dataclasses import dataclass
from enum import Enum
from functools import cached_property

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

log = logging.getLogger(__name__)

# What a platform authenticator puts on every request, in bytes because raw ASGI headers are.
# The id header names the signed-in *person* for a delegated token — measured 19 August 2026.
PRINCIPAL_ID_HEADER = b"x-ms-client-principal-id"
PRINCIPAL_NAME_HEADER = b"x-ms-client-principal-name"
PRINCIPAL_HEADER = b"x-ms-client-principal"

# The token claim naming the application the token was issued to: `azp` in v2, `appid` in v1, and Easy
# Auth's long URI form. Deliberately not `oid` or `sub`: those name the person, and this admits programs.
APPLICATION_CLAIMS = (
    "azp",
    "appid",
    "http://schemas.microsoft.com/identity/claims/appid",
)

UNAUTHENTICATED = "anonymous"


def calling_application(headers: dict[bytes, bytes]) -> str | None:
    """The application identifier this request was issued to, or `None`. `None` is a refusal, never a
    pass: it is exactly the request a record has nothing to say about."""
    raw = headers.get(PRINCIPAL_HEADER)
    if not raw:
        return None
    try:
        padded = raw + b"=" * (-len(raw) % 4)
        blob = json.loads(base64.b64decode(padded).decode("utf-8"))
    except (ValueError, binascii.Error):
        # A blob that will not decode is not an identity; it is a header to ignore.
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
    """The three kinds of path an application here serves."""

    TOOLS = "tools"
    REST = "rest"
    OPEN = "open"


def _as_pattern(template: str) -> re.Pattern[str]:
    """`/candles/{symbol}` as a regex matching one path segment per placeholder."""
    parts = [re.escape(part) for part in re.split(r"\{[^}]+\}", template)]
    return re.compile("^" + "[^/]+".join(parts) + "$")


@dataclass(frozen=True)
class Record:
    """One module's answer to "which caller may reach which surface". Every field is a difference
    the five copies actually had; nothing else differed, which is why this class can exist.

    `open_paths` is matched by equality — a set that grows is a set someone has to read — and
    `rest_paths` is written out rather than read off `app.routes`, because a record derived from the
    application can never disagree with it, and disagreeing is the whole job.
    """

    open_paths: frozenset[str]
    rest_paths: tuple[str, ...]
    # `None` for a module that publishes no tool surface. Nobody is that today; the alternative was
    # a prefix no path can start with, which reads as a mistake rather than as an absence.
    tools_prefix: str | None = "/mcp"
    # Said to a caller that arrives before the lifespan has put settings on the state. Each module
    # names itself here, because the operator reading it is not told which process answered.
    starting_detail: str = "the module is still starting"

    @cached_property
    def _rest_patterns(self) -> tuple[re.Pattern[str], ...]:
        return tuple(_as_pattern(template) for template in self.rest_paths)

    def surface_for(self, path: str) -> Surface | None:
        """Which surface this path belongs to, or `None` for a path the record does not name."""
        if path in self.open_paths:
            return Surface.OPEN
        if self.tools_prefix is not None and (
            path == self.tools_prefix or path.startswith(f"{self.tools_prefix}/")
        ):
            return Surface.TOOLS
        # A trailing slash is the same route to Starlette's redirect and a different string here;
        # normalized so `/pairs/` cannot read as a path nobody recorded. Deliberately *not* applied
        # to `open_paths`: `/ping/` reaching an unauthenticated path is the one direction where
        # being generous costs something, and two of the five copies were generous by accident.
        normalized = path.rstrip("/") or "/"
        if any(pattern.match(path) or pattern.match(normalized) for pattern in self._rest_patterns):
            return Surface.REST
        return None


class CallerAccess:
    """The record, applied in front of the whole application. Holds `app.state` rather than a
    `Settings`: this is built while `create_app()` runs, and the lifespan fills the state later."""

    def __init__(self, app: ASGIApp, state, record: Record) -> None:
        self._app = app
        self._state = state
        self._record = record

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self._app(scope, receive, send)
            return

        path = scope.get("path", "")
        surface = self._record.surface_for(path)

        if surface is None:
            log.warning("request refused: %s is not in the caller-access record", path)
            await self._refuse(scope, receive, send, 403, "this path is not open to any caller")
            return

        if surface is Surface.OPEN:
            await self._app(scope, receive, send)
            return

        # A WebSocket that is not an open path is refused here rather than left to the route:
        # `RequireCallerIdentity` passes the whole scope through, which would cost this one a hole.
        settings = getattr(self._state, "settings", None)
        if settings is None:
            # The lifespan puts them there before anything serves, so a running process does not
            # reach this. "The settings were missing" must never be the reading that allows all.
            log.error("request refused: settings are not on the application state yet")
            await self._refuse(scope, receive, send, 503, self._record.starting_detail)
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

        allowed = settings.tool_caller_ids if surface is Surface.TOOLS else settings.rest_caller_ids
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
        """One refusal, in whichever shape the connection can carry. The body matches each module's
        `contract.Problem`, so a refused caller reads the same shape as from any route."""
        if scope["type"] == "websocket":
            # 1008 is what `/ws/candles` closes a ticketless handshake with; a refusal
            # arriving in two different shapes for one reason is a refusal nobody handles.
            await send({"type": "websocket.close", "code": 1008, "reason": detail})
            return
        response = JSONResponse({"detail": detail}, status_code=status)
        await response(scope, receive, send)
