"""Who is calling.

Minimal on purpose: this module resolves every caller to one constant identity, which is
exactly correct for local work (specs/agent-browser-access, "Konfiguracja lokalna").
Reading a real principal from Easy Auth's headers and honouring
`REQUIRE_AUTHENTICATED_PRINCIPAL` is a later task group's job (specs/agent-browser-
access, "Moduł nie bierze na wiarę warstwy przed sobą") — this function's signature is
what every route already calls, so that group changes this file and nothing that calls
it.
"""

from __future__ import annotations

from fastapi import Request

LOCAL_PRINCIPAL = "local"


def current_principal(request: Request) -> str:
    return LOCAL_PRINCIPAL
