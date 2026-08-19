"""Which caller may reach which surface of this application.

The platform's own gate answers a narrower question than it looks like it does: Easy Auth
authorizes an **application** (`allowed_applications` in `infra/app-service.tf`), and once a
caller is through that door every path in this process is behind it. That was harmless while
this module served one surface to one consumer. It stopped being harmless the day the tool
surface moved in: letting `agent` and `teams` in so they can call eleven read-only tools
would, with nothing else in the way, also let them start collecting a pair and delete one.

So the record below is not a second copy of Easy Auth's list. It is the thing Easy Auth
cannot express — route by route, which identity has business there:

- the tool callers (`agent`, `teams`) reach `/mcp` and nothing else;
- the REST caller (the terminal) reaches the REST contract and never `/mcp`;
- two paths are open with no identity at all, each for a reason written beside it.

**A path not in the record is refused, not passed.** The default matters more than any
single entry: a new REST route added next month would otherwise be reachable by the agent
on the day it is written, and nothing would say so.

Raw ASGI, not `BaseHTTPMiddleware`, and that is load-bearing rather than stylistic:
`BaseHTTPMiddleware` buffers a response body in some Starlette versions, which would break
the streamable-http transport `/mcp` is served over. `tc_mcp_kit.network_identity` carries
the same constraint for the same reason, with tests that read its source.
"""

from __future__ import annotations

import logging
import re
from enum import Enum

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

log = logging.getLogger(__name__)

# What a platform authenticator puts on every request it lets through. Same pair
# `routers/stream.py` reads, in bytes because raw ASGI headers are bytes.
PRINCIPAL_ID_HEADER = b"x-ms-client-principal-id"
PRINCIPAL_NAME_HEADER = b"x-ms-client-principal-name"

UNAUTHENTICATED = "anonymous"


class Surface(str, Enum):
    """The three kinds of path this application serves."""

    TOOLS = "tools"
    REST = "rest"
    # Reachable with no identity even where the requirement is on.
    OPEN = "open"


# Both of these are outside Easy Auth in production (`infra/app-service.tf`,
# `excluded_paths`), which is exactly why they are named here rather than left to a
# prefix rule:
#
#   /ping        answers a constant. It reads nothing, so its answer cannot vary with
#                anything the archive holds — that is what makes it exemptible at all.
#   /ws/candles  cannot carry a header: a browser does not put one on a WebSocket
#                handshake. Its defence is the single-use ticket minted at
#                `POST /stream-tickets`, which *is* behind the requirement
#                (specs/market-data-browser-access).
#
# The test on this set asserts equality, not membership, so **any** addition here fails
# CI — including one that carries data, which is the case the assertion exists for.
OPEN_PATHS = frozenset({"/ping", "/ws/candles"})

# The mount, and everything the MCP transport hangs below it.
TOOLS_PREFIX = "/mcp"

# Every REST path this module publishes, as its route template. Written out rather than
# read off `app.routes` on purpose: a record derived from the application can never
# disagree with it, and disagreeing is the whole job — `test_caller_access.py` holds this
# list against the published document, so a new route fails a test until somebody decides
# which surface it belongs to.
REST_PATHS: tuple[str, ...] = (
    "/",
    "/health",
    "/asset-classes",
    "/candles/{symbol}",
    "/candles/{symbol}/forming",
    "/coverage/{symbol}",
    "/deletions",
    "/indicators",
    "/indicators/{symbol}",
    "/instruments",
    "/instruments/search",
    "/jobs",
    "/jobs/estimate",
    "/jobs/{job_id}",
    "/jobs/{job_id}/retry",
    "/pairs",
    "/pairs/{symbol}",
    "/stream-tickets",
    # FastAPI's own, published by the framework rather than by a router. They describe
    # the REST contract, so they belong to the caller that consumes it.
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
    "/openapi.json",
)


def _as_pattern(template: str) -> re.Pattern[str]:
    """`/candles/{symbol}` as a regex matching one path segment per placeholder."""
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
    # here; normalized so `/pairs/` cannot read as a path nobody recorded.
    normalized = path.rstrip("/") or "/"
    if any(pattern.match(path) or pattern.match(normalized) for pattern in _REST_PATTERNS):
        return Surface.REST
    return None


class CallerAccess:
    """The record, applied in front of the whole application.

    Holds `app.state` rather than a `Settings`: this is built while `create_app()` runs
    and the settings are put on the state by the lifespan, long afterwards. The same
    lateness `ToolContext` works around, for the same reason.
    """

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
            await self._refuse(
                scope, receive, send, 403, "this path is not open to any caller"
            )
            return

        if surface is Surface.OPEN:
            await self._app(scope, receive, send)
            return

        # A WebSocket that is not one of the open paths is refused here rather than left
        # to the route: `RequireCallerIdentity` passes the whole `websocket` scope through,
        # which costs a module with no WebSockets nothing and would cost this one a hole
        # (design.md, D4).
        settings = getattr(self._state, "settings", None)
        if settings is None:
            # The lifespan puts them there before anything serves, so this is not a state a
            # running process reaches. Refused rather than passed anyway: "the settings were
            # missing" must never be the reading under which everything is allowed.
            log.error("request refused: settings are not on the application state yet")
            await self._refuse(scope, receive, send, 503, "the archive is still starting")
            return

        headers = dict(scope.get("headers", []))
        identity = (
            (headers.get(PRINCIPAL_ID_HEADER) or headers.get(PRINCIPAL_NAME_HEADER) or b"")
            .decode("utf-8", errors="replace")
            .strip()
        )

        if not settings.require_authenticated_principal:
            # Local work: nothing stands in front, so there is no identity to have and no
            # list to be on. Logged as such rather than silently — a deployed instance
            # printing this line is a misconfiguration somebody needs to see.
            log.info("request on %s from %s", path, identity or UNAUTHENTICATED)
            await self._app(scope, receive, send)
            return

        if not identity:
            log.warning("request refused: no authenticated principal on %s", path)
            await self._refuse(scope, receive, send, 401, "not authenticated")
            return

        allowed = (
            settings.tool_caller_ids if surface is Surface.TOOLS else settings.rest_caller_ids
        )
        if identity not in allowed:
            # The identity, never the credential it arrived with, and never the request.
            log.warning("request refused: %s has no access to %s (%s)", identity, path, surface)
            await self._refuse(
                scope, receive, send, 403, f"this caller has no access to {surface.value}"
            )
            return

        log.info("request on %s from %s", path, identity)
        await self._app(scope, receive, send)

    async def _refuse(
        self, scope: Scope, receive: Receive, send: Send, status: int, detail: str
    ) -> None:
        """One refusal, in whichever shape the connection can carry.

        The body matches `contract.Problem` — a refused caller reads the same shape here
        as it would from any route that turned it down.
        """
        if scope["type"] == "websocket":
            # 1008 is what `/ws/candles` closes a ticketless handshake with; a refusal
            # arriving in two different shapes for one reason is a refusal nobody handles.
            await send({"type": "websocket.close", "code": 1008, "reason": detail})
            return
        response = JSONResponse({"detail": detail}, status_code=status)
        await response(scope, receive, send)
