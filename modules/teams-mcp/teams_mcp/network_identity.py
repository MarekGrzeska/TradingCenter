"""Who may call this module over the network — a deliberate twin of `market_mcp/
network_identity.py` and `trading_mcp/network_identity.py`, copied rather than shared (no
shared library between modules).

This checks **who is calling**, not in whose name — the second question is `operator.py`'s
and is asked per tool, not per connection. Both have to be answered before anything reaches
`teams`, and neither substitutes for the other: a caller this module trusts is still not
allowed to act for an operator it cannot name.

Raw ASGI middleware, not Starlette's `BaseHTTPMiddleware` — the streamable-http
transport streams its response, and `BaseHTTPMiddleware` buffers a response body in
some Starlette versions, which would break exactly the transport this wraps.

Mirrors market-data's and market-mcp's own check: same headers, same anonymous
sentinel, same reasoning — a platform authenticator populates these headers after
validating a token, and this module does not take that on trust
(specs/teams-mcp-transport, "Wołający jest jeden i jest nazwany").
"""

from __future__ import annotations

import logging

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

log = logging.getLogger(__name__)

PRINCIPAL_ID_HEADER = b"x-ms-client-principal-id"
PRINCIPAL_NAME_HEADER = b"x-ms-client-principal-name"
UNAUTHENTICATED = "anonymous"

# Reachable with no identity even when the requirement is on — the platform's own
# probe carries none (specs/teams-mcp-transport, "Zdrowie modułu da się sprawdzić
# bez sesji MCP").
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
