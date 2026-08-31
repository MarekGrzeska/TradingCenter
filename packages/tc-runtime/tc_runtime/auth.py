"""Who is calling, as a platform authenticator says it. The setting that decides whether a missing
principal is refused arrives as an argument, not by reaching into a caller's settings object."""

from __future__ import annotations

import logging

from fastapi import HTTPException, Request

log = logging.getLogger(__name__)

# What a platform authenticator puts on every request it lets through. The id is the
# stable half — a name can be changed, an object id cannot.
PRINCIPAL_ID_HEADER = "X-MS-CLIENT-PRINCIPAL-ID"
PRINCIPAL_NAME_HEADER = "X-MS-CLIENT-PRINCIPAL-NAME"

# Assigned when nobody stands in front of the module — reachable only while the module's
# own `require_authenticated_principal` is off, which means local development.
UNAUTHENTICATED = "anonymous"


def principal_from(request: Request, *, required: bool) -> str:
    """The caller's identity, or `UNAUTHENTICATED` when none is demanded. Refusing here refuses a request
    before it reaches a route body, which lets a module turn the requirement on without an audit."""
    identity = (
        request.headers.get(PRINCIPAL_ID_HEADER) or request.headers.get(PRINCIPAL_NAME_HEADER) or ""
    ).strip()

    if identity:
        return identity

    if required:
        log.warning("request refused: no authenticated principal")
        raise HTTPException(status_code=401, detail="not authenticated")

    return UNAUTHENTICATED
