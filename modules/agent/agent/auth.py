"""Who is calling.

Same two headers and the same fallback as `market_data/routers/stream.py`'s own Easy
Auth handling — duplicated, not imported, for the reason every cross-module borrowing
here is (no shared library, docs/architecture.md).
"""

from __future__ import annotations

import logging

from fastapi import HTTPException, Request

log = logging.getLogger(__name__)

# What a platform authenticator puts on every request it lets through. The id is the
# stable half — a name can be changed, an object id cannot.
PRINCIPAL_ID_HEADER = "X-MS-CLIENT-PRINCIPAL-ID"
PRINCIPAL_NAME_HEADER = "X-MS-CLIENT-PRINCIPAL-NAME"

# Assigned when nobody stands in front of the module — reachable only while
# `require_authenticated_principal` is off, which means local development
# (specs/agent-browser-access, "Konfiguracja lokalna").
UNAUTHENTICATED = "anonymous"


def current_principal(request: Request) -> str:
    """A `Depends()` used by every session route — raising here refuses a request
    before it ever reaches a route body, so `REQUIRE_AUTHENTICATED_PRINCIPAL` refuses
    before a model is ever touched (specs/agent-browser-access, "Moduł nie bierze na
    wiarę warstwy przed sobą")."""
    settings = request.app.state.settings
    identity = (
        request.headers.get(PRINCIPAL_ID_HEADER) or request.headers.get(PRINCIPAL_NAME_HEADER) or ""
    ).strip()

    if identity:
        return identity

    if settings.require_authenticated_principal:
        log.warning("request refused: no authenticated principal")
        raise HTTPException(status_code=401, detail="not authenticated")

    return UNAUTHENTICATED
