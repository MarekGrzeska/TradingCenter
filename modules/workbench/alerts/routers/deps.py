"""The things every route reaches for: a connection, the refusals in one shape, and the guard that keeps the routes only
the process itself may call from being called by anyone else."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import HTTPException, Request, status
from tc_runtime.caller_access import IN_PROCESS_CALLER
from tc_runtime.db import Conn

from ..contract import Defect, Problem
from ..gateway import GatewayUnreachable

# How long a request waits for a free connection before it is told the package is busy.
ACQUIRE_TIMEOUT_SECONDS = 5.0


def refusal(code: int, detail: str, defects: list[Defect] | None = None) -> HTTPException:
    return HTTPException(code, detail=Problem(detail=detail, defects=defects or []).model_dump())


def refused_rule(defects: list[Defect]) -> HTTPException:
    """A rule that could not work, with every reason at once — a form that learns one at a time is a form to give up on."""
    return refusal(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        f"the rule cannot work as written: {defects[0].message}" + (f" (and {len(defects) - 1} more)" if len(defects) > 1 else ""),
        defects,
    )


def not_found(what: str) -> HTTPException:
    return refusal(status.HTTP_404_NOT_FOUND, what)


def door_down(error: GatewayUnreachable) -> HTTPException:
    return refusal(status.HTTP_503_SERVICE_UNAVAILABLE, f"{error} — the recipient could not be checked, so nothing was saved")


def only_the_process(request: Request) -> None:
    """For the routes a producer calls. The caller record admits the operator's application to every REST path, and
    these are not for the operator: an announcement or an event accepted from the internet is a message on the
    operator's phone written by a stranger. A scope key cannot be put there by a request — only by the process."""
    if not request.scope.get(IN_PROCESS_CALLER):
        raise refusal(status.HTTP_403_FORBIDDEN, "this route is for the packages of this process, not for a caller")


@asynccontextmanager
async def connection(pool) -> AsyncIterator[Conn]:
    """A pooled connection, or a refusal the caller can act on."""
    try:
        async with pool.acquire(timeout=ACQUIRE_TIMEOUT_SECONDS) as conn:
            yield conn
    except TimeoutError as err:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=Problem(detail=f"the package is busy and no database connection came free within {ACQUIRE_TIMEOUT_SECONDS:.0f}s").model_dump(),
        ) from err
