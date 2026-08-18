"""Who is calling, as a platform authenticator says it.

One copy of what `agent/auth.py` and `teams/auth.py` each carried — measured 86.4%
identical on 18 August 2026, and the difference was prose in every line of it. The same
two headers are read a third time in `market_data/routers/stream.py`, inline; that one is
not moved here, because it is four lines inside a WebSocket route rather than a file.

The setting that decides whether a missing principal is refused belongs to the module, so
it arrives as an argument rather than being read from `app.state` here: a package that
reached into a caller's settings object by attribute name would be coupling with no
contract, which is the thing this package exists to avoid rather than to spread.
"""

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
    """The caller's identity, or `UNAUTHENTICATED` when none is demanded.

    Refusing here refuses a request before it ever reaches a route body, which is what
    lets a module turn its authentication requirement on without auditing its routes.
    """
    identity = (
        request.headers.get(PRINCIPAL_ID_HEADER) or request.headers.get(PRINCIPAL_NAME_HEADER) or ""
    ).strip()

    if identity:
        return identity

    if required:
        log.warning("request refused: no authenticated principal")
        raise HTTPException(status_code=401, detail="not authenticated")

    return UNAUTHENTICATED
