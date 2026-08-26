"""Who is calling — this module's binding of `tc_runtime.auth`. What stays here is the half the package
must not know: which of *this* module's settings decides that a missing principal is a refusal."""

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
    """A `Depends()` used by every session route — raising here refuses a request before it reaches a
    route body, so the requirement refuses before a model is ever touched."""
    return principal_from(
        request, required=request.app.state.agent.settings.require_authenticated_principal
    )
