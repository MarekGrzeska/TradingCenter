"""Running a team: the trace, the statuses, the ceiling on time, and who is watching. Everything is written as it happens,
because a run that broke in the middle is a result too — and the registry lives in this one worker, on purpose."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import asyncpg

from .. import store
from ..config import Settings
from ..contract import AgentDefinition, TeamDefinition
from ..models_catalogue import ModelCatalogue
from ..provider import ModelProvider
from ..tools import (
    MemoryScope,
    ToolAccessError,
    ToolOutcome,
    ToolOutcomeKind,
    ToolPlan,
    ToolServerRegistry,
    plan_tools,
)
from .cost import CostGuard, CostLimitReached, limit_from
from .graph import AgentFailed, compile_team
from .loop import RecordedCall, briefing_for, run_agent
from .trading import OrderTooLarge, TradeGuard, TradeLimitReached

log = logging.getLogger(__name__)



@dataclass(frozen=True)
class StepStarted:
    agent_key: str


@dataclass(frozen=True)
class StepFinished:
    agent_key: str
    status: str
    output: str | None


@dataclass(frozen=True)
class ToolCalled:
    agent_key: str
    call: RecordedCall


@dataclass(frozen=True)
class RunFinished:
    status: str
    stopped_reason: str | None


RunEvent = StepStarted | StepFinished | ToolCalled | RunFinished


class RunRegistry:
    """The running runs of this process, and who is watching each. Queues are unbounded and written with
    `put_nowait`, which is the whole of "a dropped viewer does not stop the run"."""

    def __init__(self) -> None:
        self._tasks: dict[int, asyncio.Task] = {}
        self._watchers: dict[int, set[asyncio.Queue]] = {}

    def register(self, run_id: int, task: asyncio.Task) -> None:
        self._tasks[run_id] = task
        # A task nothing references is eligible for collection mid-run; this dict is that
        # reference, and the callback is what stops it being a leak.
        task.add_done_callback(lambda _: self._tasks.pop(run_id, None))

    def is_running(self, run_id: int) -> bool:
        return run_id in self._tasks

    def cancel(self, run_id: int) -> bool:
        """Asks the run to stop. `execute_run` is what writes the status — reporting "cancelled" from the
        route would tell the operator a run had stopped before anything had recorded that it did."""
        task = self._tasks.get(run_id)
        if task is None:
            return False
        task.cancel()
        return True

    def subscribe(self, run_id: int) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._watchers.setdefault(run_id, set()).add(queue)
        return queue

    def unsubscribe(self, run_id: int, queue: asyncio.Queue) -> None:
        watchers = self._watchers.get(run_id)
        if watchers is None:
            return
        watchers.discard(queue)
        if not watchers:
            self._watchers.pop(run_id, None)

    def publish(self, run_id: int, event: RunEvent | None) -> None:
        """`None` is the end of the stream — sent after the last event so a watcher can
        close rather than wait out a timeout."""
        for queue in tuple(self._watchers.get(run_id, ())):
            queue.put_nowait(event)


_TIME_LIMIT_REASON = "the run exceeded its time limit"
_CANCELLED_REASON = "the operator interrupted the run"


async def execute_run(
    pool: asyncpg.Pool,
    *,
    run_id: int,
    team_id: int,
    owner_principal: str,
    definition: TeamDefinition,
    provider: ModelProvider,
    tool_registry: ToolServerRegistry,
    catalogue: ModelCatalogue,
    settings: Settings,
    registry: RunRegistry,
) -> None:
    """The whole of a run, from `pending` to one of `completed`, `failed`, `cancelled`. Never raises for
    anything the run itself did. `CancelledError` goes back out after the status is written."""
    async with pool.acquire() as conn:
        await store.mark_run_running(conn, run_id=run_id)

    status = "failed"
    reason: str | None = "the run ended without a result"
    try:
        try:
            # Before anything else, and before a single agent is called: a team that assigns no tools
            # never touches a server, and one that does is refused here rather than three agents in.
            plan = await plan_tools(
                definition,
                tool_registry,
                # Which team is remembering, on whose behalf, in which run — bound onto the in-process
                # tools here, because this is the first point where all three are known together.
                memory=MemoryScope(
                    team_id=team_id, owner_principal=owner_principal, run_id=run_id
                ),
            )
        except ToolAccessError as err:
            # Named as tool access rather than as a generic failure, and refused before a single agent is
            # called: nothing is paid for a run that cannot check anything.
            status, reason = "failed", f"tool access: {err}"
            return

        # One guard of each kind for the whole run, shared by every agent in it: both ceilings are on
        # what the *run* does, not on what any one role does.
        guard = CostGuard(limit_from(definition.limits.run_limit))
        trades = TradeGuard(definition.trading)
        run = _Run(
            pool=pool,
            run_id=run_id,
            plan=plan,
            provider=provider,
            catalogue=catalogue,
            registry=registry,
            guard=guard,
            trades=trades,
        )
        graph = compile_team(definition, run.run_agent_step)
        try:
            await asyncio.wait_for(
                graph.ainvoke({"outputs": {}}), timeout=settings.run_timeout_seconds
            )
        except TimeoutError:
            status, reason = "failed", _TIME_LIMIT_REASON
            return
        except CostLimitReached as err:
            # Failed, and the reason names the number — an operator whose run stopped over money asks
            # "how much of what". Everything written up to here stays.
            status, reason = "failed", str(err)
            return
        except TradeLimitReached as err:
            # A separate branch from the one above, and the sentence is the difference: an operator reads
            # "orders" and learns their team wanted to trade more than they allowed.
            status, reason = "failed", str(err)
            return
        except AgentFailed as err:
            status, reason = "failed", str(err)
            return
        except Exception as err:
            # A broken run is a status, not a crash: whatever went wrong outside an agent's own work
            # still leaves a trace and a reason rather than a task that vanished.
            log.exception("run %s failed outside an agent's own work", run_id)
            status, reason = "failed", f"the run failed: {err}"
            return
        status, reason = "completed", None
    except asyncio.CancelledError:
        status, reason = "cancelled", _CANCELLED_REASON
        # Shielded, because this task is already cancelled: without it the first await raises again and
        # the run is left `running` for ever, which is the state start-up cleans up after a crash.
        await asyncio.shield(_close(pool, run_id=run_id, status=status, reason=reason, registry=registry))
        raise
    finally:
        if status != "cancelled":
            await _close(pool, run_id=run_id, status=status, reason=reason, registry=registry)


async def _close(
    pool: asyncpg.Pool,
    *,
    run_id: int,
    status: str,
    reason: str | None,
    registry: RunRegistry,
) -> None:
    """One status, one set of closing rows, one last event. A step still `running` is closed as failed; one
    still `pending` stays pending, because saying it failed would put work in the trace nobody attempted."""
    async with pool.acquire() as conn:
        await store.fail_running_steps(conn, run_id=run_id)
        closed = await store.finish_run(conn, run_id=run_id, status=status, stopped_reason=reason)
    if closed is None:
        # Somebody else closed it first — an interruption landing just as the time limit
        # did. Their account stands; this one is dropped rather than announced.
        return
    registry.publish(run_id, RunFinished(status=status, stopped_reason=reason))
    registry.publish(run_id, None)


@dataclass(frozen=True)
class _Run:
    """What every agent in one run shares: the pool, the plan, the two guards, and the id everything points
    at. Frozen because none of it changes during a run; what does belongs to one step."""

    pool: asyncpg.Pool
    run_id: int
    plan: ToolPlan
    provider: ModelProvider
    catalogue: ModelCatalogue
    registry: RunRegistry
    guard: CostGuard
    trades: TradeGuard

    async def run_agent_step(
        self, agent: AgentDefinition, given: Sequence[tuple[str, str]]
    ) -> str:
        return await _StepRunner(self, agent).run(given)


class _StepRunner:
    """One agent's step: the row it writes, the guards it asks, and the trade it holds while waiting. `pending_trade` was
    a `nonlocal` between two closures; one instance per agent per run is what makes a plain field correct."""

    def __init__(self, run: _Run, agent: AgentDefinition) -> None:
        self._run = run
        self._agent = agent
        self._entry = run.catalogue.get(agent.model_id)
        self._pending_trade: int | None = None

    async def run(self, given: Sequence[tuple[str, str]]) -> str:
        run = self._run
        agent = self._agent
        async with run.pool.acquire() as conn:
            self._step = await store.start_step(conn, run_id=run.run_id, agent_key=agent.key)
        run.registry.publish(run.run_id, StepStarted(agent_key=agent.key))

        work = await run_agent(
            agent,
            model=self._entry.model,
            briefing=briefing_for(agent, given),
            provider=run.provider,
            tools=run.plan.for_agent(agent.key),
            # Bound to this agent, so the plan can refuse a name this agent was not assigned — being
            # offered a narrower list is not the same as being held to it.
            call_tool=self._call_tool,
            on_tool_call=self._on_tool_call,
            before_model_call=self._before_model_call,
            on_model_call=self._on_model_call,
            before_write_call=self._before_write_call,
            moves_the_account=run.plan.moves_the_account,
        )

        async with run.pool.acquire() as conn:
            if work.failed:
                await store.finish_step(
                    conn, step_id=self._step["id"], status="failed", output=None, rounds=work.rounds
                )
            else:
                await store.finish_step(
                    conn,
                    step_id=self._step["id"],
                    status="completed",
                    output=work.text,
                    rounds=work.rounds,
                )

        if work.failed:
            run.registry.publish(
                run.run_id, StepFinished(agent_key=agent.key, status="failed", output=None)
            )
            raise AgentFailed(agent.key, "the model call failed")

        run.registry.publish(
            run.run_id, StepFinished(agent_key=agent.key, status="completed", output=work.text)
        )
        if work.ceiling_reached:
            log.info(
                "agent %s in run %s reached the round ceiling and answered without tools",
                agent.key,
                run.run_id,
            )
        return work.text

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
        return await self._run.plan.call(name, arguments, agent_key=self._agent.key)

    async def _on_tool_call(self, call: RecordedCall) -> None:
        run = self._run
        async with run.pool.acquire() as conn:
            await store.record_tool_call(
                conn,
                run_id=run.run_id,
                run_step_id=self._step["id"],
                round_index=call.round_index,
                position=call.position,
                tool_name=call.name,
                arguments=call.arguments,
                outcome=call.outcome,
                result_text=call.text,
                duration_ms=call.duration_ms,
            )
            if self._pending_trade is not None:
                settlement = _read_settlement(call)
                await store.settle_trade(
                    conn,
                    trade_id=self._pending_trade,
                    status=settlement.status,
                    result_status=settlement.result_status,
                    provider_order_id=settlement.order_id,
                    reference=settlement.reference,
                )
                self._pending_trade = None
        run.registry.publish(run.run_id, ToolCalled(agent_key=self._agent.key, call=call))

    async def _before_write_call(self, name: str, arguments: dict) -> str | None:
        """The order ceiling, and the row that outlives whatever happens next. Order matters twice: the
        guard is asked first, so a refused call leaves no row; and the row is written before the call goes out."""
        run = self._run
        try:
            run.trades.check(arguments)
        except OrderTooLarge as err:
            # Refused to the model as this one call; the run goes on, because a size is
            # something the agent can correct.
            return str(err)

        async with run.pool.acquire() as conn:
            row = await store.record_trade(
                conn,
                run_id=run.run_id,
                run_step_id=self._step["id"],
                agent_key=self._agent.key,
                tool_name=name,
                symbol=_text_arg(arguments, "symbol"),
                direction=_text_arg(arguments, "direction"),
                size=_decimal_arg(arguments, "size"),
                level=_decimal_arg(arguments, "level"),
            )
        self._pending_trade = row["id"]
        run.trades.placing()
        return None

    async def _before_model_call(self) -> None:
        self._run.guard.check()

    async def _on_model_call(self, usage) -> None:
        """One row per model call, written as the call finishes rather than when the agent does — which is
        what makes the guard's own total current enough to stop the *next* call."""
        run = self._run
        async with run.pool.acquire() as conn:
            row = await store.record_usage(
                conn,
                run_id=run.run_id,
                run_step_id=self._step["id"],
                model_id=self._entry.id,
                input_tokens=usage.input_tokens if usage else None,
                output_tokens=usage.output_tokens if usage else None,
                cached_tokens=usage.cached_tokens if usage else None,
                reasoning_tokens=usage.reasoning_tokens if usage else None,
                input_rate_per_1m=self._entry.input_rate_per_1m,
                output_rate_per_1m=self._entry.output_rate_per_1m,
            )
        run.guard.add(row["cost"])


# Best effort by design, and the trace is why: `tool_calls` already holds the arguments and the reply
# verbatim. This is the queryable half, and a shape that changed upstream degrades to nulls, not to no row.


@dataclass(frozen=True)
class _Settlement:
    status: str
    result_status: str | None = None
    order_id: str | None = None
    reference: str | None = None


def _read_settlement(call: RecordedCall) -> _Settlement:
    """What the trade row should say now that the call has come back. `unknown` is the answer whenever the
    reply does not establish otherwise, an outcome this module cannot parse included."""
    if call.outcome == str(ToolOutcomeKind.UNAVAILABLE):
        # The call failed in a way that says nothing about whether it arrived — the one
        # case the whole "row before the call" arrangement exists for.
        return _Settlement("unknown")
    if call.outcome == str(ToolOutcomeKind.REFUSED):
        # The server answered no. `trading-mcp` refuses before touching the account for a bad request and
        # turns a provider REJECTED into a refusal too. Its access-failure refusals say so themselves.
        if "access failure" in call.text:
            return _Settlement("unknown")
        return _Settlement("refused")

    try:
        payload = json.loads(call.text)
    except (TypeError, ValueError):
        return _Settlement("unknown")
    if not isinstance(payload, dict):
        return _Settlement("unknown")

    outcome = payload.get("outcome")
    if outcome not in ("settled", "unsettled"):
        return _Settlement("unknown")
    return _Settlement(
        status=outcome,
        result_status=_as_text(payload.get("status")),
        order_id=_as_text(payload.get("id")),
        reference=_as_text(payload.get("reference")),
    )


def _as_text(value: object) -> str | None:
    return None if value is None else str(value)


def _text_arg(arguments: dict, key: str) -> str | None:
    value = arguments.get(key)
    return None if value is None else str(value)


def _decimal_arg(arguments: dict, key: str) -> Decimal | None:
    value = arguments.get(key)
    if value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    # The column refuses a non-positive size, and a model is free to ask for one — dropped to NULL rather
    # than allowed to fail the insert, which would cost a trace row over an argument about to be refused.
    return parsed if key != "size" or parsed > 0 else None
