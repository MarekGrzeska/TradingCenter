"""The one-time conversion of what the operator had set before this package.

It runs once — the marker is written in the same transaction as the rules — and it runs while the old ways still work, so
the rules it makes sit idle until the producers are switched over to them. The neighbours it reads start after this package
does, so it asks until they answer; if they never do it writes no marker and is tried at the next start: converting from
half a picture is worse than converting later."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import asyncpg

from . import legacy, store
from .legacy import LegacySource

log = logging.getLogger(__name__)

MARKER = "legacy-alert-settings"


# How long it waits for the neighbours to be serving: a minute of start-up is generous, and then it leaves it to the next start.
ATTEMPTS = 60
PAUSE_SECONDS = 2.0


async def run_when_ready(pool: asyncpg.Pool, source: LegacySource | None, *, pause: float = PAUSE_SECONDS) -> int:
    """`run`, asked again while the neighbours are not yet able to answer. Returns what `run` last returned."""
    for _ in range(ATTEMPTS):
        outcome = await run(pool, source)
        if outcome is not None:
            return outcome
        await asyncio.sleep(pause)
    log.warning("the old alert settings could not be read in %d tries; the conversion will be tried at the next start", ATTEMPTS)
    return 0


async def run(pool: asyncpg.Pool, source: LegacySource | None) -> int | None:
    """How many rules were made. Zero is an answer: nothing was set, or it was already done. `None` is that the neighbours
    could not be asked yet."""
    if source is None:
        return 0
    async with pool.acquire() as conn:
        if await store.done(conn, MARKER):
            return 0
    try:
        old = await source.read()
    except Exception:
        log.exception("could not read the old alert settings")
        return None
    if old is None:
        return None

    rules = legacy.plan(old)
    now = datetime.now(UTC)
    async with pool.acquire() as conn, conn.transaction():
        # Re-checked inside the transaction: two instances starting together must not both convert.
        await conn.execute("SELECT pg_advisory_xact_lock($1)", CONVERSION_LOCK)
        if await store.done(conn, MARKER):
            return 0
        for name, (description, schema) in legacy.PLACEHOLDER_TYPES.items():
            await store.ensure_event_type(conn, name, description=description, schema=schema)
        for rule in rules:
            await store.insert_rule(conn, rule, created_by="conversion", now=now)
        await store.mark_done(conn, MARKER)
    log.info("converted the old alert settings into %d rule(s)", len(rules))
    return len(rules)


# Its own key beside the migration's 8120, so the conversion waits for no migration and a migration for no conversion.
CONVERSION_LOCK = 8121
