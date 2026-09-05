"""The one thing every route reaches for. Kept apart from `app.py` so a router never imports the
module that mounts it."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import HTTPException, status
from tc_runtime.db import Conn

# How long a request waits for a free connection before it is told the archive is busy. `acquire()`
# without one waits for ever, and a browser has no deadline of its own: the tab spins until the
# platform's own 230 s idle cut, which reads as the module being down rather than being loaded.
ACQUIRE_TIMEOUT_SECONDS = 5.0


@asynccontextmanager
async def connection(pool) -> AsyncIterator[Conn]:
    """A pooled connection, or a refusal the caller can render. 503 and not 500: nothing is wrong
    with the request, and the terminal's own notice already offers the retry that answer deserves."""
    try:
        async with pool.acquire(timeout=ACQUIRE_TIMEOUT_SECONDS) as conn:
            yield conn
    except TimeoutError as err:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "the archive is busy and no database connection came free within "
                f"{ACQUIRE_TIMEOUT_SECONDS:.0f}s — this read was not attempted"
            ),
        ) from err
