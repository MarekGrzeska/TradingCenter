"""The module's own clock: waking, claiming a due schedule or trigger exactly once, and starting the run each fire calls
for. Two concerns share one wake because both end in `start_run_on_revision` and a row in `schedule_fires`."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import operator as op
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
from tc_runtime.db import Conn

from .. import store
from ..config import Settings
from ..models_catalogue import ModelCatalogue
from ..provider import ModelProvider
from ..runner import RunRegistry, start_run_on_revision
from ..runner.cost import CostLimitReached
from ..runner.trading import TradeLimitReached
from ..tools import ToolOutcomeKind, ToolServer, ToolServerRegistry, ToolServerUnavailable
from ..validation import DefinitionRefused
from .timing import fires_after

log = logging.getLogger(__name__)

_RUN_IN_PROGRESS = ("pending", "running")

_COMPARISONS: dict[str, Callable[[float, float], bool]] = {
    "gt": op.gt,
    "gte": op.ge,
    "lt": op.lt,
    "lte": op.le,
    "eq": op.eq,
}


@dataclass(frozen=True)
class _Deps:
    """Everything a fire needs that is not the row itself. None of the five is read by the clock — they are
    what `start_run_on_revision` wants, and they travelled as five keyword arguments through every signature."""

    catalogue: ModelCatalogue
    provider: ModelProvider
    tool_registry: ToolServerRegistry
    settings: Settings
    registry: RunRegistry


class Clock:
    """Owns exactly one background task, started in `app.py`'s `lifespan` and stopped
    with it — the same shape `ToolServerRegistry`'s own lifetime already has."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        *,
        catalogue: ModelCatalogue,
        provider: ModelProvider,
        tool_registry: ToolServerRegistry,
        settings: Settings,
        registry: RunRegistry,
    ) -> None:
        self._pool = pool
        self._settings = settings
        self._deps = _Deps(
            catalogue=catalogue,
            provider=provider,
            tool_registry=tool_registry,
            settings=settings,
            registry=registry,
        )
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        # The lever the spec calls for: cleared and restarted, every schedule and trigger is exactly where
        # it was, and a run started by hand still works — this is the one thing that does not happen.
        if not self._settings.scheduler_enabled:
            log.info(
                "the clock is disabled (SCHEDULER_ENABLED=false) — no schedule or "
                "trigger will fire on its own"
            )
            return
        self._task = asyncio.create_task(self._run_forever())

    async def aclose(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task

    async def _run_forever(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                log.exception("the clock's own tick failed — trying again next wake")
            await asyncio.sleep(self._settings.scheduler_poll_interval_seconds)

    async def tick(self) -> list[asyncio.Task[None]]:
        """One wake: every due schedule, then every due trigger. Public so a test can drive it without
        waiting on the poll interval, and it returns the tracking tasks so a test can wait for every write."""
        tasks: list[asyncio.Task[None]] = []
        async with self._pool.acquire() as conn:
            due_schedules = await store.list_due_schedules(conn)
        for schedule in due_schedules:
            task = await self._attempt(
                _fire_schedule, dict(schedule), what=f"schedule {schedule['id']}"
            )
            if task is not None:
                tasks.append(task)

        async with self._pool.acquire() as conn:
            due_triggers = await store.list_due_triggers(conn)
        for trigger in due_triggers:
            task = await self._attempt(
                _check_trigger, dict(trigger), what=f"trigger {trigger['id']}"
            )
            if task is not None:
                tasks.append(task)
        return tasks

    async def _attempt(
        self,
        handler: Callable[[asyncpg.Pool, Mapping[str, Any], _Deps], Any],
        row: dict[str, Any],
        *,
        what: str,
    ) -> asyncio.Task[None] | None:
        """One row's turn, with its own failure contained to itself. The wake works every operator's
        schedules, so an exception escaping one would silence all the ones after it, and silently."""
        try:
            return await handler(self._pool, row, self._deps)
        except Exception:
            log.exception("%s failed this wake — the rest of the wake carries on", what)
            return None



async def _resolve_revision(conn: asyncpg.pool.PoolConnectionProxy, *, row: Mapping[str, Any]):
    """The revision a schedule or trigger would run — both carry the same revision-selection shape."""
    if row["revision_mode"] == "pinned":
        return await store.get_revision_by_id(
            conn, revision_id=row["pinned_revision_id"], owner_principal=row["owner_principal"]
        )
    return await store.get_latest_revision(
        conn, team_id=row["team_id"], owner_principal=row["owner_principal"]
    )


async def _start_from(
    pool: asyncpg.Pool, *, row: Mapping[str, Any], deps: _Deps
) -> tuple[asyncpg.Record, asyncio.Task[None]] | str:
    """Resolves the revision and starts a run on it, or returns the refusal reason as a string instead of
    raising — every caller writes that string into a `schedule_fires` row."""
    async with pool.acquire() as conn:
        revision_row = await _resolve_revision(conn, row=row)
    if revision_row is None:
        return "the revision this schedule or trigger points at no longer exists"
    revision = dict(revision_row)

    try:
        return await start_run_on_revision(
            pool,
            revision=revision,
            owner_principal=row["owner_principal"],
            catalogue=deps.catalogue,
            provider=deps.provider,
            tool_registry=deps.tool_registry,
            settings=deps.settings,
            registry=deps.registry,
        )
    # The ceilings are caught by their *base* classes, not the two daily ones a route names. A route may
    # enumerate; here an uncaught ceiling leaves the fire with no row and takes the rest of the wake down.
    except (DefinitionRefused, CostLimitReached, TradeLimitReached) as err:
        return str(err)


class _ScheduleSource:
    """A claimed row as the shared tail sees it: what to call it, and the four `store` calls that name it. No shared base,
    deliberately — it would be five `raise NotImplementedError` bodies standing in for what the union already says."""

    kind = "schedule"

    def __init__(self, row_id: int) -> None:
        self.id = row_id

    async def latest_run_status(self, conn: Conn) -> str | None:
        return await store.latest_run_status_for_schedule(conn, schedule_id=self.id)

    async def record_fire(
        self,
        conn: Conn,
        *,
        outcome: str,
        reason: str | None = None,
        run_id: int | None = None,
        skipped_count: int = 0,
    ) -> None:
        await store.record_fire(
            conn,
            schedule_id=self.id,
            outcome=outcome,
            reason=reason,
            run_id=run_id,
            skipped_count=skipped_count,
        )

    async def reset_failures(self, conn: Conn) -> asyncpg.Record | None:
        return await store.reset_schedule_failures(conn, schedule_id=self.id)

    async def increment_failures(self, conn: Conn) -> asyncpg.Record | None:
        return await store.increment_schedule_failures(conn, schedule_id=self.id)

    async def disable_for_failures(self, conn: Conn, reason: str) -> asyncpg.Record | None:
        return await store.disable_schedule_for_failures(conn, schedule_id=self.id, reason=reason)


class _TriggerSource:
    kind = "trigger"

    def __init__(self, row_id: int) -> None:
        self.id = row_id

    async def latest_run_status(self, conn: Conn) -> str | None:
        return await store.latest_run_status_for_trigger(conn, trigger_id=self.id)

    async def record_fire(
        self,
        conn: Conn,
        *,
        outcome: str,
        reason: str | None = None,
        run_id: int | None = None,
        skipped_count: int = 0,
    ) -> None:
        await store.record_fire(
            conn,
            trigger_id=self.id,
            outcome=outcome,
            reason=reason,
            run_id=run_id,
            skipped_count=skipped_count,
        )

    async def reset_failures(self, conn: Conn) -> asyncpg.Record | None:
        return await store.reset_trigger_failures(conn, trigger_id=self.id)

    async def increment_failures(self, conn: Conn) -> asyncpg.Record | None:
        return await store.increment_trigger_failures(conn, trigger_id=self.id)

    async def disable_for_failures(self, conn: Conn, reason: str) -> asyncpg.Record | None:
        return await store.disable_trigger_for_failures(conn, trigger_id=self.id, reason=reason)


_Source = _ScheduleSource | _TriggerSource


async def _start_and_track(
    pool: asyncpg.Pool,
    source: _Source,
    claimed: Mapping[str, Any],
    *,
    deps: _Deps,
    skipped_count: int = 0,
) -> asyncio.Task[None] | None:
    """Everything after a row has been claimed and its own kind of "is it due" answered. Written once
    because every line of it was true twice — a schedule that overlaps itself doubles a team's cost."""
    async with pool.acquire() as conn:
        previous_status = await source.latest_run_status(conn)
    if previous_status in _RUN_IN_PROGRESS:
        async with pool.acquire() as conn:
            await source.record_fire(
                conn,
                outcome="skipped",
                reason=f"the previous run of this {source.kind} is still working",
                skipped_count=skipped_count,
            )
        return None

    started = await _start_from(pool, row=claimed, deps=deps)
    if isinstance(started, str):
        async with pool.acquire() as conn:
            await source.record_fire(
                conn, outcome="skipped", reason=started, skipped_count=skipped_count
            )
        return None

    run, task = started
    async with pool.acquire() as conn:
        await source.record_fire(
            conn, outcome="started", run_id=run["id"], skipped_count=skipped_count
        )
    return asyncio.create_task(
        _track_run(
            pool,
            task=task,
            run_id=run["id"],
            source=source,
            failure_threshold=deps.settings.scheduler_failure_threshold,
        )
    )



def _next_fire_and_skipped(
    cron_expression: str, due_at: datetime, now: datetime
) -> tuple[datetime, int]:
    """The schedule's new `next_fire_at` — the first cron slot strictly after `now` — and how many slots
    between the claimed value and now were folded into this one fire."""
    skipped = 0
    for candidate in fires_after(cron_expression, due_at):
        if candidate <= now:
            skipped += 1
        else:
            return candidate, skipped
    raise AssertionError("fires_after never runs out")


async def _fire_schedule(
    pool: asyncpg.Pool, schedule: Mapping[str, Any], deps: _Deps
) -> asyncio.Task[None] | None:
    """Returns the failure-streak tracking task when a run actually started, so a caller that cares can
    await it instead of guessing with a sleep. `Clock.tick()` lets it run detached."""
    now = datetime.now(UTC)
    next_fire_at, skipped = _next_fire_and_skipped(
        schedule["cron_expression"], schedule["next_fire_at"], now
    )

    async with pool.acquire() as conn:
        claimed_row = await store.claim_due_schedule(
            conn, schedule_id=schedule["id"], next_fire_at=next_fire_at
        )
    if claimed_row is None:
        # Another process already claimed this fire, or it was disabled between being listed as due and
        # this call — either way, nothing further belongs to this attempt.
        return
    # asyncpg's Record forwards mapping access at runtime but is not a `Mapping` to a
    # type checker (contract.py's own `from_row` callers hit the same thing).
    claimed = dict(claimed_row)
    return await _start_and_track(
        pool,
        _ScheduleSource(claimed["id"]),
        claimed,
        deps=deps,
        skipped_count=skipped,
    )



def _walk(payload: Any, field_path: str) -> Any:
    """Dotted-path access into whatever a tool call answered with. `None` for any step that does not
    resolve, which the caller treats the same as a server that could not be asked."""
    current = payload
    for segment in field_path.split("."):
        if isinstance(current, list):
            try:
                current = current[int(segment)]
            except (ValueError, IndexError):
                return None
        elif isinstance(current, dict):
            current = current.get(segment)
        else:
            return None
    return current


async def _server_announcing(
    servers: list[ToolServer], tool_name: str
) -> ToolServer | None:
    """The first configured server that publishes this name, or `None` — covering both "nobody announces
    it" and "nobody could be asked". A trigger treats those the way it treats a refused call."""
    for server in servers:
        try:
            tools = await server.list_tools()
        except ToolServerUnavailable:
            continue
        if any(tool.name == tool_name for tool in tools):
            return server
    return None


async def _evaluate_condition(
    trigger: Mapping[str, Any], *, tool_registry: ToolServerRegistry
) -> tuple[bool | None, str | None]:
    """`(result, unavailable_reason)` — `result` is `None` exactly when the reason is set. All three
    silences are one fact from a trigger's seat: it did not learn what the market is doing."""
    configured = tool_registry.configured()
    if not configured:
        return None, (
            "no tool server is configured (neither MARKET_MCP_URL nor TRADING_MCP_URL "
            "is set), so the condition could not be read"
        )

    arguments = trigger["arguments"]
    if isinstance(arguments, str):
        arguments = json.loads(arguments)

    # Which server owns the name is asked here rather than assumed: since phase 2 there are two, and a
    # trigger names one tool without saying whose. The list is cached, so this costs one round trip.
    server = await _server_announcing(configured, trigger["tool_name"])
    if server is None:
        return None, (
            f"no configured tool server announces {trigger['tool_name']!r}, "
            "or none could be asked"
        )

    outcome = await server.call(trigger["tool_name"], arguments)
    if outcome.kind is ToolOutcomeKind.UNAVAILABLE:
        return None, f"the tool server could not be asked: {outcome.text}"
    if outcome.kind is ToolOutcomeKind.REFUSED:
        return None, f"the tool refused the call: {outcome.text}"

    try:
        payload = json.loads(outcome.text)
    except (json.JSONDecodeError, TypeError):
        return None, f"the tool's answer was not structured data field_path can read: {outcome.text[:200]!r}"

    value = _walk(payload, trigger["field_path"])
    if not isinstance(value, int | float) or isinstance(value, bool):
        return None, f"field_path {trigger['field_path']!r} did not resolve to a number in the tool's answer"

    return _COMPARISONS[trigger["comparison"]](float(value), float(trigger["threshold"])), None


async def _check_trigger(
    pool: asyncpg.Pool, trigger: Mapping[str, Any], deps: _Deps
) -> asyncio.Task[None] | None:
    """Mirrors `_fire_schedule`'s own return: the failure-streak tracking task when a
    run actually started, `None` otherwise."""
    now = datetime.now(UTC)
    next_check_at = now + timedelta(seconds=trigger["poll_interval_seconds"])

    async with pool.acquire() as conn:
        claimed_row = await store.claim_trigger_for_check(
            conn, trigger_id=trigger["id"], next_check_at=next_check_at
        )
    if claimed_row is None:
        return
    claimed = dict(claimed_row)
    trigger_id = claimed["id"]
    source = _TriggerSource(trigger_id)

    # Evaluating the condition never calls a model — one tool call, nothing charged to this team's usage —
    # so a trigger checked every few seconds costs nothing until it fires.
    result, unavailable_reason = await _evaluate_condition(
        claimed, tool_registry=deps.tool_registry
    )
    if unavailable_reason is not None:
        async with pool.acquire() as conn:
            await store.record_trigger_check(conn, trigger_id=trigger_id, result=None, fired=False)
            await source.record_fire(
                conn, outcome="unavailable", reason=unavailable_reason
            )
        return None

    # A fire is the `false -> true` transition, not the state itself: a reading that stays true for the
    # next ten checks fires nothing ten more times.
    edge = bool(result) and not bool(claimed["last_result"])
    last_fired_at = claimed["last_fired_at"]
    cooldown_seconds = claimed["cooldown_seconds"]
    cooldown_active = (
        last_fired_at is not None and (now - last_fired_at).total_seconds() < cooldown_seconds
    )
    # `fired` only advances past the cooldown gate — an edge suppressed by cooldown MUST NOT reset the
    # window, or a condition flickering faster than the cooldown would never clear it.
    proceeding = edge and not cooldown_active

    async with pool.acquire() as conn:
        await store.record_trigger_check(conn, trigger_id=trigger_id, result=result, fired=proceeding)

    if not edge:
        return None
    if cooldown_active:
        async with pool.acquire() as conn:
            await source.record_fire(
                conn,
                outcome="skipped",
                reason=f"cooldown active — the last fire was less than {cooldown_seconds}s ago",
            )
        return None

    return await _start_and_track(pool, source, claimed, deps=deps)



async def _track_run(
    pool: asyncpg.Pool,
    *,
    task: asyncio.Task[None],
    run_id: int,
    source: _Source,
    failure_threshold: int,
) -> None:
    """Waits for a run this clock started to finish, then moves the failure streak that decides whether its
    schedule keeps working unattended. `cancelled` moves neither way: it is a supervised choice."""
    try:
        await task
        async with pool.acquire() as conn:
            status = await store.get_run_status(conn, run_id=run_id)
        if status == "completed":
            async with pool.acquire() as conn:
                await source.reset_failures(conn)
        elif status == "failed":
            async with pool.acquire() as conn:
                row = await source.increment_failures(conn)
            if row is not None and row["consecutive_failures"] >= failure_threshold:
                async with pool.acquire() as conn:
                    await source.disable_for_failures(
                        conn,
                        f"{failure_threshold} kolejne przebiegi zakończone niepowodzeniem",
                    )
    except Exception:
        log.exception("could not record the outcome of run %d for its schedule/trigger", run_id)
