"""The package's one clock: wakes, looks at the value rules whose turn has come, and sleeps again. A published event
wakes it early, so an alert about a film does not wait out the tick.

Looking costs a tool call and nothing else — no model is asked, and nothing is charged for a look that finds no news."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
from tc_runtime.liveness import LoopHeartbeat

from . import conditions, store, template
from .catalog import ToolSource
from .config import Settings
from .delivery import Deliverer
from .gateway import Gateway

log = logging.getLogger(__name__)

# How many value rules one tick takes. The rest wait for the next: a tick that grows with the list of rules is a tick
# that stops being a tick.
BATCH = 50
# How many of them are looked at at once. A look is a read against an archive in this process, so this is a courtesy to
# the archive's pool and not a limit of ours.
CONCURRENCY = 5
CLEANUP_EVERY = timedelta(hours=1)


class Clock:
    def __init__(
        self,
        pool: asyncpg.Pool,
        settings: Settings,
        tools: ToolSource | None,
        heartbeat: LoopHeartbeat,
        gateway: Gateway | None = None,
    ) -> None:
        self._pool = pool
        self._settings = settings
        self._tools = tools
        self._heartbeat = heartbeat
        self.deliverer = Deliverer(pool, settings, gateway)
        self._woken = asyncio.Event()
        self._last_cleanup: datetime | None = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="alerts-clock")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    def wake(self) -> None:
        self._woken.set()

    async def _run(self) -> None:
        while True:
            try:
                await self.tick()
                self._heartbeat.beat()
            except asyncio.CancelledError:
                raise
            except Exception:
                # A tick that raised is a tick that did not happen, and the heartbeat is how that is noticed.
                log.exception("the alerts clock could not finish a tick")
            try:
                await asyncio.wait_for(self._woken.wait(), timeout=self._settings.tick_seconds)
            except TimeoutError:
                pass
            self._woken.clear()

    async def tick(self, now: datetime | None = None) -> int:
        """One wake: every value rule that is due, looked at, and every message that is due, sent. Public so a test can drive
        it. Returns how many rules were looked at."""
        moment = now or datetime.now(UTC)
        async with self._pool.acquire() as conn:
            due = await store.claim_due(conn, limit=BATCH, now=moment)
        gate = asyncio.Semaphore(CONCURRENCY)

        async def one(row: asyncpg.Record) -> None:
            async with gate:
                try:
                    await self._check(row, moment)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception("rule %s could not be looked at", row["id"])

        await asyncio.gather(*(one(row) for row in due))
        await self.deliverer.run(moment)
        await self._forget_old_events(moment)
        return len(due)

    async def _forget_old_events(self, now: datetime) -> None:
        """Once an hour: events past their retention go, the fires they caused stay."""
        if self._last_cleanup is not None and now - self._last_cleanup < CLEANUP_EVERY:
            return
        self._last_cleanup = now
        async with self._pool.acquire() as conn:
            gone = await store.delete_events_before(conn, now - timedelta(days=self._settings.event_retention_days))
        if gone:
            log.info("forgot %d event(s) older than %d days", gone, self._settings.event_retention_days)

    async def _check(self, row: asyncpg.Record, now: datetime) -> None:
        arguments = store.json_of(row["arguments"]) or {}
        seen = await conditions.look(
            self._tools,
            tool_name=row["tool_name"],
            arguments=arguments,
            field_path=row["field_path"],
            comparison=row["comparison"],
            threshold=float(row["threshold"]),
        )
        verdict = conditions.decide(
            seen,
            known=row["last_known_result"],
            last_fired_at=row["last_fired_at"],
            cooldown_seconds=row["cooldown_seconds"],
            now=now,
        )
        async with self._pool.acquire() as conn, conn.transaction():
            await store.record_look(conn, row["id"], result=seen.result, now=now)
            if seen.result is None:
                await self._note_silence(conn, row, seen, now)
            elif verdict.cooled:
                await store.record_check(
                    conn,
                    row["id"],
                    outcome="cooldown",
                    reason=f"the value crossed the level inside the {row['cooldown_seconds']} s cool-down of the last alert",
                    now=now,
                )
            elif verdict.fire:
                await store.record_fire(
                    conn,
                    row["id"],
                    edge_at=now,
                    text=template.render(row["template"], _values(row, arguments, seen)),
                    value=seen.value,
                    now=now,
                )

    async def _note_silence(self, conn: Any, row: asyncpg.Record, seen: conditions.Look, now: datetime) -> None:
        """An outage is one line in the history, not one line a look: written when the rule goes quiet or its reason
        changes, so the list of what happened to a rule stays a list of what happened."""
        previous = await store.last_check(conn, row["id"])
        still_the_same = (
            row["last_result"] is None
            and row["last_checked_at"] is not None
            and previous is not None
            and (previous["outcome"], previous["reason"]) == (seen.outcome, seen.reason)
        )
        if not still_the_same:
            assert seen.reason is not None
            await store.record_check(conn, row["id"], outcome=seen.outcome, reason=seen.reason, now=now)


def _values(row: asyncpg.Record, arguments: dict[str, Any], seen: conditions.Look) -> dict[str, Any]:
    """What the message of a value rule can say: the fixed names, then the scalars the rule was given (the symbol, mostly)."""
    scalars = {
        name: value for name, value in arguments.items() if isinstance(value, str | int | float | bool) and name.isidentifier()
    }
    return {
        **scalars,
        "rule": row["name"],
        "value": seen.value,
        "threshold": float(row["threshold"]),
        "comparison": conditions.COMPARISON_WORDS[row["comparison"]],
        "tool": row["tool_name"],
        "field": row["field_path"],
    }
