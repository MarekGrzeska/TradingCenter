"""The two things every route reaches for: a connection, and the translation from this module's
refusals into HTTP.

Kept apart from `app.py` so a router never imports the module that mounts it, and kept in one file so
the mapping is read once rather than guessed at route by route.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import HTTPException, status
from tc_runtime.db import Conn

from ..contract import Problem
from ..errors import (
    Blocked,
    CreatingBotsUnavailable,
    CreatorBotUnreadable,
    DestinationNotReady,
    GatewayError,
    MessageTooLong,
    NoSuchDestination,
    RateLimited,
    TelegramRefused,
    TelegramUnreachable,
    TooManyBots,
)

# How long a request waits for a free connection before it is told the gateway is busy. `acquire()`
# without one waits for ever, and a caller sending an alert has a loop to get back to.
ACQUIRE_TIMEOUT_SECONDS = 5.0

# Which refusal becomes which status, and the reason each caller needs is in `cause` rather than in
# the number: 502 for "Telegram said no" separates a bad request here from a bad answer there.
_STATUS: tuple[tuple[type[GatewayError], int, str, bool], ...] = (
    (NoSuchDestination, status.HTTP_404_NOT_FOUND, "request", False),
    (DestinationNotReady, status.HTTP_409_CONFLICT, "module", False),
    (Blocked, status.HTTP_409_CONFLICT, "telegram", False),
    (MessageTooLong, status.HTTP_422_UNPROCESSABLE_CONTENT, "request", False),
    (RateLimited, status.HTTP_429_TOO_MANY_REQUESTS, "telegram", True),
    (TooManyBots, status.HTTP_409_CONFLICT, "module", False),
    # Not 500: this deployment cannot create bots at all, which is a configuration the module
    # supports rather than something that broke in this request.
    (CreatingBotsUnavailable, status.HTTP_501_NOT_IMPLEMENTED, "module", False),
    (CreatorBotUnreadable, status.HTTP_502_BAD_GATEWAY, "telegram", False),
    (TelegramRefused, status.HTTP_502_BAD_GATEWAY, "telegram", False),
    (TelegramUnreachable, status.HTTP_502_BAD_GATEWAY, "telegram", True),
)


def refusal(error: GatewayError) -> HTTPException:
    """One of this module's refusals as HTTP, carrying its own words.

    The text is the error's, never a summary: the caller logs this, and a sentence this file invented
    would describe the gateway rather than the failure.
    """
    for kind, code, cause, retryable in _STATUS:
        if isinstance(error, kind):
            problem = Problem(
                detail=str(error),
                cause=cause,  # pyright: ignore[reportArgumentType]
                retryable=retryable,
                retry_after_seconds=(
                    error.retry_after_seconds if isinstance(error, RateLimited) else None
                ),
            )
            return HTTPException(code, detail=problem.model_dump())
    return HTTPException(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=Problem(detail=str(error)).model_dump(),
    )


def bad_request(detail: str) -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=Problem(detail=detail, cause="request").model_dump(),
    )


def conflict(detail: str) -> HTTPException:
    return HTTPException(
        status.HTTP_409_CONFLICT, detail=Problem(detail=detail, cause="request").model_dump()
    )


def not_found(detail: str) -> HTTPException:
    return HTTPException(
        status.HTTP_404_NOT_FOUND, detail=Problem(detail=detail, cause="request").model_dump()
    )


@asynccontextmanager
async def connection(pool) -> AsyncIterator[Conn]:
    """A pooled connection, or a refusal the caller can act on. 503 and not 500: nothing is wrong
    with the request, and a caller that retries next loop is the shape this module was built for."""
    try:
        async with pool.acquire(timeout=ACQUIRE_TIMEOUT_SECONDS) as conn:
            yield conn
    except TimeoutError as err:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=Problem(
                detail=(
                    "the gateway is busy and no database connection came free within "
                    f"{ACQUIRE_TIMEOUT_SECONDS:.0f}s — nothing was sent"
                ),
                retryable=True,
            ).model_dump(),
        ) from err
