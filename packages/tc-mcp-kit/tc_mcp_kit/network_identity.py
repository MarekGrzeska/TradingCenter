"""Who may call this module over the network — not in whose name, which belongs to a module that has
one. Raw ASGI, not `BaseHTTPMiddleware`: that buffers a body, and this wraps a streaming transport."""

from __future__ import annotations

import logging

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

log = logging.getLogger(__name__)

PRINCIPAL_ID_HEADER = b"x-ms-client-principal-id"
PRINCIPAL_NAME_HEADER = b"x-ms-client-principal-name"
UNAUTHENTICATED = "anonymous"

# Reachable with no identity even when the requirement is on — the platform's own
# probe carries none (each module names the requirement in its own spec).
EXEMPT_PATHS = {"/health"}


class RequireCallerIdentity:
    def __init__(self, app: ASGIApp, require_authenticated_principal: bool) -> None:
        self._app = app
        self._require = require_authenticated_principal

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") in EXEMPT_PATHS:
            await self._app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        identity = (
            (headers.get(PRINCIPAL_ID_HEADER) or headers.get(PRINCIPAL_NAME_HEADER) or b"")
            .decode("utf-8", errors="replace")
            .strip()
        )

        if not identity:
            if self._require:
                log.info("request refused: no authenticated principal on %s", scope.get("path"))
                response = JSONResponse({"error": "not authenticated"}, status_code=401)
                await response(scope, receive, send)
                return
            identity = UNAUTHENTICATED

        log.info("request on %s from %s", scope.get("path"), identity)
        await self._app(scope, receive, send)
