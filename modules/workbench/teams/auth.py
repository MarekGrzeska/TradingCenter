"""Who is calling — this module's binding of `tc_runtime.auth`.

The reading of the two Easy Auth headers is shared (`tc_runtime/auth.py`, one copy of what
this file and `agent/auth.py` each carried). What stays here is the half the package must
not know: which of *this* module's settings decides that a missing principal is a refusal
(specs/teams-browser-access, "Moduł nie bierze na wiarę warstwy przed sobą").
"""

from __future__ import annotations

from fastapi import Request
from tc_runtime.auth import (
    PRINCIPAL_ID_HEADER,
    PRINCIPAL_NAME_HEADER,
    UNAUTHENTICATED,
    principal_from,
)

__all__ = ["PRINCIPAL_ID_HEADER", "PRINCIPAL_NAME_HEADER", "UNAUTHENTICATED", "current_principal"]


def current_principal(request: Request) -> str:
    """A `Depends()` used by every owned-resource route — raising here refuses a request
    before it ever reaches a route body, so `REQUIRE_AUTHENTICATED_PRINCIPAL` refuses
    before a model is ever touched."""
    return principal_from(
        request, required=request.app.state.teams.settings.require_authenticated_principal
    )
