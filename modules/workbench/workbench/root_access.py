"""Which application may reach this process's own routes — the conversation and the teams, everything not under a
package's prefix. Easy Auth authorizes an application, not a route, and since stage 4 of
`one-process-per-security-boundary` it admits one caller the root must never answer: the operator's `az`, there for
`/telegram`'s bots and destinations alone. Each package keeps its own record; this is the record of what is left.
"""

from __future__ import annotations

import logging

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send
from tc_runtime.caller_access import IN_PROCESS_CALLER, calling_application

log = logging.getLogger(__name__)

# Reachable with no identity: the deploy probe's route, which Easy Auth excludes too.
OPEN_PATHS = frozenset({"/health"})


class RootCallers:
    """Refuses, on a root path, every application not on the process's REST list. A package's path passes through
    untouched: its own `CallerAccess` decides there, against its own list."""

    def __init__(self, app: ASGIApp, *, state, package_prefixes: frozenset[str]) -> None:
        self._app = app
        self._state = state
        self._prefixes = package_prefixes

    def _is_root(self, path: str) -> bool:
        return not any(path == prefix or path.startswith(prefix + "/") for prefix in self._prefixes)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] != "http" or path in OPEN_PATHS or not self._is_root(path):
            await self._app(scope, receive, send)
            return

        settings = getattr(self._state, "settings", None)
        if settings is None:
            # "The settings were missing" must never be the reading that allows all.
            await _refuse(scope, receive, send, 503, "the workbench is still starting")
            return
        if scope.get(IN_PROCESS_CALLER) or not settings.require_authenticated_principal:
            await self._app(scope, receive, send)
            return

        application = calling_application(dict(scope.get("headers", [])))
        if application is None:
            log.warning("request refused: the calling application cannot be named on %s", path)
            await _refuse(scope, receive, send, 401, "not authenticated")
            return
        if application not in _identifiers(settings.rest_caller_application_ids):
            log.warning("request refused: application %s has no access to %s", application, path)
            await _refuse(scope, receive, send, 403, "this caller has no access to the workbench")
            return
        await self._app(scope, receive, send)


def _identifiers(raw: str) -> frozenset[str]:
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


async def _refuse(scope: Scope, receive: Receive, send: Send, status: int, detail: str) -> None:
    await JSONResponse({"detail": detail}, status_code=status)(scope, receive, send)
