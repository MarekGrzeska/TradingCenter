"""The module's own clock: waking on its own, claiming a due schedule or trigger exactly
once, and starting the run each fire calls for — the same sequence `POST
/teams/{id}/runs` runs, minus the click (design.md, "Zegar w procesie modułu, nie w
Azure").

Two independent concerns share one wake rather than two tasks: a schedule fires on time,
a trigger fires on a market condition's edge, and both end the same way — a call to
`runner.start_run_on_revision` and a row in `schedule_fires`. `_fire_schedule` and
`_check_trigger` stay separate functions because what decides "is this due" differs (a
cron expression against the clock, a tool call against the market), not because the two
need separate clocks, separate polling loops, or separate safety rails — both share the
same overlap check, the same daily-limit and unattended-tool refusal, and the same
failure-streak tracking.

Every step here reads a row already claimed by this process (`store.claim_due_schedule`,
`store.claim_trigger_for_check`) — the conditional `UPDATE` is the entire exactly-once
guarantee (design.md, "Wyzwolenie przejmowane w bazie, nie posiadane przez proces"), so
nothing below needs a lock of its own.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import operator as op
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
from croniter import croniter

from .. import store
from ..config import Settings
from ..models_catalogue import ModelCatalogue
from ..provider import ModelProvider
from ..runner import RunRegistry, start_run_on_revision
from ..runner.cost import CostLimitReached
from ..runner.trading import TradeLimitReached
from ..tools import ToolOutcomeKind, ToolServer, ToolServerRegistry, ToolServerUnavailable
from ..validation import DefinitionRefused

log = logging.getLogger(__name__)

_RUN_IN_PROGRESS = ("pending", "running")

_COMPARISONS: dict[str, Callable[[float, float], bool]] = {
    "gt": op.gt,
    "gte": op.ge,
    "lt": op.lt,
    "lte": op.le,
    "eq": op.eq,
}


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
        self._catalogue = catalogue
        self._provider = provider
        self._tool_registry = tool_registry
        self._settings = settings
        self._registry = registry
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        # The lever specs/teams-schedules calls for: cleared and restarted, every
        # schedule and trigger is exactly where it was, and a run started by hand still
        # works — this is the one thing that does not happen.
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
        """One wake: every due schedule, then every due trigger. Public so a test can
        drive it without waiting on `scheduler_poll_interval_seconds`.

        Returns the failure-streak tracking task for every fire that actually started a
        run, so a test can `asyncio.gather(*tasks)` and know every write this wake will
        ever make has happened before it moves on — `_run_forever` discards the list and
        lets them run detached, which is the right shape in production: nothing is
        waiting on a wake to finish.
        """
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
        handler: Callable[..., Any],
        row: dict[str, Any],
        *,
        what: str,
    ) -> asyncio.Task[None] | None:
        """One row's turn, with its own failure contained to itself.

        The wake works every operator's schedules, so an exception escaping one of them
        would silence all the ones after it in the same list — and silently, since the
        row that failed never reaches `record_fire` either. `_run_forever` still catches
        whatever gets past this; that outer net is for the wake itself (the two `SELECT`s
        above), not for one row.
        """
        try:
            return await handler(
                self._pool,
                row,
                catalogue=self._catalogue,
                provider=self._provider,
                tool_registry=self._tool_registry,
                settings=self._settings,
                registry=self._registry,
            )
        except Exception:
            log.exception("%s failed this wake — the rest of the wake carries on", what)
            return None


# --- shared by both -------------------------------------------------------------------


async def _resolve_revision(conn: asyncpg.pool.PoolConnectionProxy, *, row: Mapping[str, Any]):
    """The revision a schedule or trigger would run — both carry the same
    `revision_mode`/`pinned_revision_id`/`team_id`/`owner_principal` shape
    (`store._SCHEDULE_COLUMNS`, `store._TRIGGER_COLUMNS`)."""
    if row["revision_mode"] == "pinned":
        return await store.get_revision_by_id(
            conn, revision_id=row["pinned_revision_id"], owner_principal=row["owner_principal"]
        )
    return await store.get_latest_revision(
        conn, team_id=row["team_id"], owner_principal=row["owner_principal"]
    )


async def _start_from(
    pool: asyncpg.Pool,
    *,
    row: Mapping[str, Any],
    catalogue: ModelCatalogue,
    provider: ModelProvider,
    tool_registry: ToolServerRegistry,
    settings: Settings,
    registry: RunRegistry,
) -> tuple[asyncpg.Record, asyncio.Task[None]] | str:
    """Resolves the revision and starts a run on it, or returns the refusal reason as a
    string instead of raising — every caller here writes that string into a
    `schedule_fires` row rather than handling an exception."""
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
            catalogue=catalogue,
            provider=provider,
            tool_registry=tool_registry,
            settings=settings,
            registry=registry,
        )
    # The ceilings are caught by their *base* classes, not by the two daily ones
    # `routers/runs.py` names. A route may enumerate: an uncaught ceiling there is one
    # 500 for one operator who is watching. Here it would leave the fire with no row at
    # all and take the rest of the wake down with it — which is how `DailyOrderLimitReached`,
    # added by phase 2 to the very function this calls, went unhandled for a whole phase.
    # A ceiling added later is caught by this on the day it is written.
    except (DefinitionRefused, CostLimitReached, TradeLimitReached) as err:
        return str(err)


# --- schedules --------------------------------------------------------------------


def _next_fire_and_skipped(
    cron_expression: str, due_at: datetime, now: datetime
) -> tuple[datetime, int]:
    """The schedule's new `next_fire_at` — the first cron slot strictly after `now` —
    and how many slots between `due_at` (the row's own value at claim time, itself
    already due) and `now` were folded into this one fire
    (specs/teams-schedules, "Pominięte wyzwolenia zwijają się do jednego")."""
    iterator = croniter(cron_expression, due_at)
    skipped = 0
    while True:
        candidate = iterator.get_next(datetime)
        if candidate <= now:
            skipped += 1
        else:
            return candidate, skipped


async def _fire_schedule(
    pool: asyncpg.Pool,
    schedule: Mapping[str, Any],
    *,
    catalogue: ModelCatalogue,
    provider: ModelProvider,
    tool_registry: ToolServerRegistry,
    settings: Settings,
    registry: RunRegistry,
) -> asyncio.Task[None] | None:
    """Returns the failure-streak tracking task when a run actually started, so a caller
    that cares when the bookkeeping is done (a test; nothing in production does) can
    await it instead of guessing with a sleep. `Clock.tick()` lets it run detached, the
    same as any other run this module starts."""
    now = datetime.now(UTC)
    next_fire_at, skipped = _next_fire_and_skipped(
        schedule["cron_expression"], schedule["next_fire_at"], now
    )

    async with pool.acquire() as conn:
        claimed_row = await store.claim_due_schedule(
            conn, schedule_id=schedule["id"], next_fire_at=next_fire_at
        )
    if claimed_row is None:
        # Another process already claimed this fire, or it was disabled between being
        # listed as due and this call (specs/teams-schedules, "Dwa procesy przy jednym
        # wyzwoleniu") — either way, nothing further belongs to this attempt.
        return
    # asyncpg's Record forwards mapping access at runtime but is not a `Mapping` to a
    # type checker (contract.py's own `from_row` callers hit the same thing).
    claimed = dict(claimed_row)
    schedule_id = claimed["id"]

    async with pool.acquire() as conn:
        previous_status = await store.latest_run_status_for_schedule(conn, schedule_id=schedule_id)
    if previous_status in _RUN_IN_PROGRESS:
        async with pool.acquire() as conn:
            await store.record_fire(
                conn,
                schedule_id=schedule_id,
                outcome="skipped",
                reason="the previous run of this schedule is still working",
                skipped_count=skipped,
            )
        return

    started = await _start_from(
        pool,
        row=claimed,
        catalogue=catalogue,
        provider=provider,
        tool_registry=tool_registry,
        settings=settings,
        registry=registry,
    )
    if isinstance(started, str):
        async with pool.acquire() as conn:
            await store.record_fire(
                conn, schedule_id=schedule_id, outcome="skipped", reason=started, skipped_count=skipped
            )
        return

    run, task = started
    async with pool.acquire() as conn:
        await store.record_fire(
            conn, schedule_id=schedule_id, outcome="started", run_id=run["id"], skipped_count=skipped
        )
    return asyncio.create_task(
        _track_run(
            pool,
            task=task,
            run_id=run["id"],
            on_completed=lambda conn: store.reset_schedule_failures(conn, schedule_id=schedule_id),
            on_failed=lambda conn: store.increment_schedule_failures(conn, schedule_id=schedule_id),
            on_threshold_reached=lambda conn, reason: store.disable_schedule_for_failures(
                conn, schedule_id=schedule_id, reason=reason
            ),
            failure_threshold=settings.scheduler_failure_threshold,
        )
    )


# --- triggers -----------------------------------------------------------------------


def _walk(payload: Any, field_path: str) -> Any:
    """Dotted-path access into whatever a tool call answered with — a plain dict/list
    walk, list segments read as an index. `None` for any step that does not resolve,
    which the caller treats the same as a server that could not be asked
    (specs/teams-triggers, "Niedostępność serwera narzędzi to nie jest niespełniony
    warunek" — a field this trigger's `field_path` cannot find is the same kind of "the
    condition could not be read" as the call itself failing)."""
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
    """The first configured server that publishes this name, or `None` — which covers
    both "nobody announces it" and "nobody could be asked". A trigger treats those the
    same way it treats a refused call: it did not learn what the market is doing, so it
    MUST NOT fire (specs/teams-triggers)."""
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
    """`(result, unavailable_reason)` — `result` is `None` exactly when
    `unavailable_reason` is set. A server that could not be asked, one that refused the
    call, and an answer with no such field are all the same fact from a trigger's own
    seat: it did not learn what the market is doing, so it MUST NOT fire either way. The
    reason text is what tells the two apart on the way to `schedule_fires`."""
    configured = tool_registry.configured()
    if not configured:
        return None, (
            "no tool server is configured (neither MARKET_MCP_URL nor TRADING_MCP_URL "
            "is set), so the condition could not be read"
        )

    arguments = trigger["arguments"]
    if isinstance(arguments, str):
        arguments = json.loads(arguments)

    # Which server owns the name is asked here rather than assumed: since phase 2 there
    # are two, and a trigger names one tool without saying whose. The list is read once
    # per session and cached in the client, so this costs a round trip on the first tick
    # after a restart and nothing afterwards.
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
    pool: asyncpg.Pool,
    trigger: Mapping[str, Any],
    *,
    catalogue: ModelCatalogue,
    provider: ModelProvider,
    tool_registry: ToolServerRegistry,
    settings: Settings,
    registry: RunRegistry,
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

    # Evaluating the condition never calls a model — one tool call, nothing charged to
    # this team's usage (specs/teams-triggers, "Obserwowanie rynku nie kosztuje tokenów
    # modelu") — so a trigger checked every few seconds costs nothing until it fires.
    result, unavailable_reason = await _evaluate_condition(claimed, tool_registry=tool_registry)
    if unavailable_reason is not None:
        async with pool.acquire() as conn:
            await store.record_trigger_check(conn, trigger_id=trigger_id, result=None, fired=False)
            await store.record_fire(
                conn, trigger_id=trigger_id, outcome="unavailable", reason=unavailable_reason
            )
        return

    # A fire is the `false -> true` transition, not the state itself — reading it stays
    # true for the next ten checks fires nothing ten more times
    # (specs/teams-triggers, "Wyzwalacz reaguje na zbocze, nie na stan").
    edge = bool(result) and not bool(claimed["last_result"])
    last_fired_at = claimed["last_fired_at"]
    cooldown_seconds = claimed["cooldown_seconds"]
    cooldown_active = (
        last_fired_at is not None and (now - last_fired_at).total_seconds() < cooldown_seconds
    )
    # `fired` (and so `last_fired_at`) only advances past the cooldown gate — an edge
    # suppressed by cooldown MUST NOT itself reset the cooldown window, or a condition
    # flickering faster than the cooldown would never actually clear it.
    proceeding = edge and not cooldown_active

    async with pool.acquire() as conn:
        await store.record_trigger_check(conn, trigger_id=trigger_id, result=result, fired=proceeding)

    if not edge:
        return
    if cooldown_active:
        async with pool.acquire() as conn:
            await store.record_fire(
                conn,
                trigger_id=trigger_id,
                outcome="skipped",
                reason=f"cooldown active — the last fire was less than {cooldown_seconds}s ago",
            )
        return

    async with pool.acquire() as conn:
        previous_status = await store.latest_run_status_for_trigger(conn, trigger_id=trigger_id)
    if previous_status in _RUN_IN_PROGRESS:
        async with pool.acquire() as conn:
            await store.record_fire(
                conn,
                trigger_id=trigger_id,
                outcome="skipped",
                reason="the previous run of this trigger is still working",
            )
        return

    started = await _start_from(
        pool,
        row=claimed,
        catalogue=catalogue,
        provider=provider,
        tool_registry=tool_registry,
        settings=settings,
        registry=registry,
    )
    if isinstance(started, str):
        async with pool.acquire() as conn:
            await store.record_fire(conn, trigger_id=trigger_id, outcome="skipped", reason=started)
        return

    run, task = started
    async with pool.acquire() as conn:
        await store.record_fire(conn, trigger_id=trigger_id, outcome="started", run_id=run["id"])
    return asyncio.create_task(
        _track_run(
            pool,
            task=task,
            run_id=run["id"],
            on_completed=lambda conn: store.reset_trigger_failures(conn, trigger_id=trigger_id),
            on_failed=lambda conn: store.increment_trigger_failures(conn, trigger_id=trigger_id),
            on_threshold_reached=lambda conn, reason: store.disable_trigger_for_failures(
                conn, trigger_id=trigger_id, reason=reason
            ),
            failure_threshold=settings.scheduler_failure_threshold,
        )
    )


# --- the failure streak, common to both --------------------------------------------


async def _track_run(
    pool: asyncpg.Pool,
    *,
    task: asyncio.Task[None],
    run_id: int,
    on_completed: Callable[[asyncpg.pool.PoolConnectionProxy], Any],
    on_failed: Callable[[asyncpg.pool.PoolConnectionProxy], Any],
    on_threshold_reached: Callable[[asyncpg.pool.PoolConnectionProxy, str], Any],
    failure_threshold: int,
) -> None:
    """Waits for a run this clock started to finish, then moves the failure streak that
    decides whether its schedule or trigger keeps working unattended
    (specs/teams-schedules, "Harmonogram po serii nieudanych przebiegów wyłącza się
    sam"). `cancelled` — an operator's own interruption — moves neither way: it is a
    supervised choice, not a signal about whether the schedule itself is healthy.
    """
    try:
        await task
        async with pool.acquire() as conn:
            status = await store.get_run_status(conn, run_id=run_id)
        if status == "completed":
            async with pool.acquire() as conn:
                await on_completed(conn)
        elif status == "failed":
            async with pool.acquire() as conn:
                row = await on_failed(conn)
            if row is not None and row["consecutive_failures"] >= failure_threshold:
                async with pool.acquire() as conn:
                    await on_threshold_reached(
                        conn,
                        f"{failure_threshold} kolejne przebiegi zakończone niepowodzeniem",
                    )
    except Exception:
        log.exception("could not record the outcome of run %d for its schedule/trigger", run_id)
