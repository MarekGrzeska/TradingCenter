"""Running a team: the trace, the statuses, the ceiling on time, and who is watching.

One function does the work (`execute_run`) and one object keeps what a running run needs
from outside itself (`RunRegistry`): the task, so an operator can interrupt it, and the
queues of whoever is watching, so progress reaches them without the run depending on any
of them being read.

Everything here is written **as it happens**, never assembled at the end. A run that broke
in the middle is a result too — more often the interesting one — and a trace written at
the end would be missing exactly when it is needed (specs/teams-runs, "Ślad przebiegu
zostaje niezależnie od tego, jak przebieg się skończył").

The registry lives in this process, which is what the deployment is: one worker, on
purpose (`infra/app-service.tf`). A second instance would need the queues to travel, and
`store.fail_unfinished_runs` — the start-up half of the same fact — is what keeps a run
whose process died from reading as one that is still working.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import asyncpg

from .. import store
from ..config import Settings
from ..contract import AgentDefinition, TeamDefinition
from ..models_catalogue import ModelCatalogue
from ..provider import ModelProvider
from ..tools import ToolAccessError, ToolOutcomeKind, ToolPlan, ToolServerRegistry, plan_tools
from .cost import CostGuard, CostLimitReached, limit_from
from .graph import AgentFailed, compile_team
from .loop import RecordedCall, briefing_for, run_agent
from .trading import OrderTooLarge, TradeGuard, TradeLimitReached

log = logging.getLogger(__name__)


# --- what a watcher sees -------------------------------------------------------------


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
    """The running runs of this process, and who is watching each.

    Queues are unbounded and written with `put_nowait`, which is the whole of "a dropped
    viewer does not stop the run" (specs/teams-runs, "Zerwanie połączenia odbierającego
    postęp MUST NOT przerwać przebiegu"): nothing here ever waits for a reader.
    """

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
        """Asks the run to stop. `execute_run` is what writes the status — cancelling here
        and reporting "cancelled" from the route would tell the operator a run had stopped
        before anything had recorded that it did."""
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


# --- running one team ----------------------------------------------------------------

_TIME_LIMIT_REASON = "the run exceeded its time limit"
_CANCELLED_REASON = "the operator interrupted the run"


async def execute_run(
    pool: asyncpg.Pool,
    *,
    run_id: int,
    definition: TeamDefinition,
    provider: ModelProvider,
    tool_registry: ToolServerRegistry,
    catalogue: ModelCatalogue,
    settings: Settings,
    registry: RunRegistry,
) -> None:
    """The whole of a run, from `pending` to one of `completed`, `failed`, `cancelled`.

    Never raises for anything the run itself did — a broken agent, an unreachable tool
    server and the time limit all end as a status with a reason. `asyncio.CancelledError`
    is the one exception that goes back out, after the status is written: swallowing it
    would tell the event loop the task chose to keep running.
    """
    async with pool.acquire() as conn:
        await store.mark_run_running(conn, run_id=run_id)

    status = "failed"
    reason: str | None = "the run ended without a result"
    try:
        try:
            # Before anything else, and before a single agent is called: a team that
            # assigns no tools never touches a server at all, and one that does is
            # refused here rather than three agents into the run. `plan` remembers
            # which server announced each assigned name, so no agent's own call needs
            # to ask again (`ToolPlan.call`).
            plan = await plan_tools(definition, tool_registry)
        except ToolAccessError as err:
            # Named as tool access rather than as a generic failure, and refused before a
            # single agent is called — nothing is paid for a run that cannot check
            # anything (specs/teams-tool-access, "Brak serwera narzędzi zatrzymuje
            # przebieg").
            status, reason = "failed", f"tool access: {err}"
            return

        # One guard of each kind for the whole run, shared by every agent in it: both
        # ceilings are on what the *run* does, not on what any one role does
        # (specs/teams-usage, specs/teams-trading).
        guard = CostGuard(limit_from(definition.limits.run_limit))
        trades = TradeGuard(definition.trading)
        graph = compile_team(
            definition,
            _agent_runner(
                pool,
                run_id=run_id,
                plan=plan,
                provider=provider,
                catalogue=catalogue,
                registry=registry,
                guard=guard,
                trades=trades,
            ),
        )
        try:
            await asyncio.wait_for(
                graph.ainvoke({"outputs": {}}), timeout=settings.run_timeout_seconds
            )
        except TimeoutError:
            status, reason = "failed", _TIME_LIMIT_REASON
            return
        except CostLimitReached as err:
            # Failed, and the reason names the number — an operator whose run stopped over
            # money has one question, and it is "how much of what" (specs/teams-usage,
            # "statusem nazywającym koszt jako przyczynę"). Everything written up to here
            # stays: a run stopped by its budget is a result like any other.
            status, reason = "failed", str(err)
            return
        except TradeLimitReached as err:
            # A separate branch from the one above, and the sentence it writes is the
            # difference: an operator reads "cost" and buys more budget, reads "orders"
            # and learns their team wanted to trade more than they allowed — which is a
            # result of the experiment, not a fault in it (specs/teams-runs, "Powód
            # zatrzymania odróżnia granicę zleceń od granicy kosztu").
            status, reason = "failed", str(err)
            return
        except AgentFailed as err:
            status, reason = "failed", str(err)
            return
        except Exception as err:
            # A broken run is a status, not a crash: whatever went wrong outside an
            # agent's own work — the graph, the pool, a bug here — still leaves a trace
            # and a reason rather than a task that vanished.
            log.exception("run %s failed outside an agent's own work", run_id)
            status, reason = "failed", f"the run failed: {err}"
            return
        status, reason = "completed", None
    except asyncio.CancelledError:
        status, reason = "cancelled", _CANCELLED_REASON
        # Shielded, because this task is already cancelled: without it the first await
        # below raises again and the run would be left `running` for ever — which is the
        # one state `store.fail_unfinished_runs` exists to clean up after a *crash*, not
        # after an interruption the module handled.
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
    """One status, one set of closing rows, one last event.

    A step still `running` is closed as failed: whatever it was doing stopped when the run
    did, and a step left claiming to work would outlive the process that could have
    finished it. A step still `pending` stays pending — it never started, and saying it
    failed would put work in the trace that nobody attempted.
    """
    async with pool.acquire() as conn:
        await store.fail_running_steps(conn, run_id=run_id)
        closed = await store.finish_run(conn, run_id=run_id, status=status, stopped_reason=reason)
    if closed is None:
        # Somebody else closed it first — an interruption landing just as the time limit
        # did. Their account stands; this one is dropped rather than announced.
        return
    registry.publish(run_id, RunFinished(status=status, stopped_reason=reason))
    registry.publish(run_id, None)


def _agent_runner(
    pool: asyncpg.Pool,
    *,
    run_id: int,
    plan: ToolPlan,
    provider: ModelProvider,
    catalogue: ModelCatalogue,
    registry: RunRegistry,
    guard: CostGuard,
    trades: TradeGuard,
):
    async def run_one(agent: AgentDefinition, given: Sequence[tuple[str, str]]) -> str:
        entry = catalogue.get(agent.model_id)
        async with pool.acquire() as conn:
            step = await store.start_step(conn, run_id=run_id, agent_key=agent.key)
        registry.publish(run_id, StepStarted(agent_key=agent.key))

        # The trade row written by `before_write_call`, waiting for the reply that
        # settles it. One variable rather than a map because one agent's calls are
        # sequential (`loop.py` walks a round's requests in order) — agents run
        # concurrently, but each holds its own `run_one` frame and its own of these.
        pending_trade: int | None = None

        async def on_tool_call(call: RecordedCall) -> None:
            nonlocal pending_trade
            async with pool.acquire() as conn:
                await store.record_tool_call(
                    conn,
                    run_id=run_id,
                    run_step_id=step["id"],
                    round_index=call.round_index,
                    position=call.position,
                    tool_name=call.name,
                    arguments=call.arguments,
                    outcome=call.outcome,
                    result_text=call.text,
                    duration_ms=call.duration_ms,
                )
                if pending_trade is not None:
                    settlement = _read_settlement(call)
                    await store.settle_trade(
                        conn,
                        trade_id=pending_trade,
                        status=settlement.status,
                        result_status=settlement.result_status,
                        provider_order_id=settlement.order_id,
                        reference=settlement.reference,
                    )
                    pending_trade = None
            registry.publish(run_id, ToolCalled(agent_key=agent.key, call=call))

        async def before_write_call(name: str, arguments: dict) -> str | None:
            """The order ceiling, and the row that outlives whatever happens next.

            Order matters twice over: the guard is asked first, so a refused call leaves
            no row for an order that was never sent; and the row is written before the
            call goes out, so an order whose reply never comes back is still in the trace
            (specs/teams-trading, "Wiersz MUST powstać przed wysłaniem wywołania").
            """
            nonlocal pending_trade
            try:
                trades.check(arguments)
            except OrderTooLarge as err:
                # Refused to the model as this one call; the run goes on, because a size
                # is something the agent can correct.
                return str(err)

            async with pool.acquire() as conn:
                row = await store.record_trade(
                    conn,
                    run_id=run_id,
                    run_step_id=step["id"],
                    agent_key=agent.key,
                    tool_name=name,
                    symbol=_text_arg(arguments, "symbol"),
                    direction=_text_arg(arguments, "direction"),
                    size=_decimal_arg(arguments, "size"),
                    level=_decimal_arg(arguments, "level"),
                )
            pending_trade = row["id"]
            trades.placing()
            return None

        async def before_model_call() -> None:
            guard.check()

        async def on_model_call(usage) -> None:
            """One row per model call, written as the call finishes rather than when the
            agent does — which is what makes the guard's own total current enough to stop
            the *next* call (specs/teams-usage)."""
            async with pool.acquire() as conn:
                row = await store.record_usage(
                    conn,
                    run_id=run_id,
                    run_step_id=step["id"],
                    model_id=entry.id,
                    input_tokens=usage.input_tokens if usage else None,
                    output_tokens=usage.output_tokens if usage else None,
                    cached_tokens=usage.cached_tokens if usage else None,
                    reasoning_tokens=usage.reasoning_tokens if usage else None,
                    input_rate_per_1m=entry.input_rate_per_1m,
                    output_rate_per_1m=entry.output_rate_per_1m,
                )
            guard.add(row["cost"])

        work = await run_agent(
            agent,
            model=entry.model,
            briefing=briefing_for(agent, given),
            provider=provider,
            tools=plan.for_agent(agent.key),
            call_tool=plan.call,
            on_tool_call=on_tool_call,
            before_model_call=before_model_call,
            on_model_call=on_model_call,
            before_write_call=before_write_call,
        )

        async with pool.acquire() as conn:
            if work.failed:
                await store.finish_step(
                    conn, step_id=step["id"], status="failed", output=None, rounds=work.rounds
                )
            else:
                await store.finish_step(
                    conn,
                    step_id=step["id"],
                    status="completed",
                    output=work.text,
                    rounds=work.rounds,
                )

        if work.failed:
            registry.publish(
                run_id, StepFinished(agent_key=agent.key, status="failed", output=None)
            )
            raise AgentFailed(agent.key, "the model call failed")

        registry.publish(
            run_id, StepFinished(agent_key=agent.key, status="completed", output=work.text)
        )
        if work.ceiling_reached:
            log.info(
                "agent %s in run %s reached the round ceiling and answered without tools",
                agent.key,
                run_id,
            )
        return work.text

    return run_one


# --- reading a write call's own arguments and reply (specs/teams-trading) -------------
#
# Best effort by design, and the trace is why: `tool_calls` already holds the arguments
# and the reply verbatim, so nothing is lost when a field cannot be read here. What this
# produces is the *queryable* half — the columns a daily count and a terminal list are
# built from — and a `place_order` shape that changed upstream must degrade to a row with
# nulls rather than to no row at all.


@dataclass(frozen=True)
class _Settlement:
    status: str
    result_status: str | None = None
    order_id: str | None = None
    reference: str | None = None


def _read_settlement(call: RecordedCall) -> _Settlement:
    """What the trade row should say now that the call has come back.

    `unknown` is the answer whenever the reply does not establish otherwise, and that
    includes an outcome this module cannot parse: an order this module cannot account for
    is exactly what the status is for (specs/teams-trading, "Wywołanie, którego skutek
    pozostał nieznany, MUST zostać zapisane jako nieznany").
    """
    if call.outcome == str(ToolOutcomeKind.UNAVAILABLE):
        # The call failed in a way that says nothing about whether it arrived — the one
        # case the whole "row before the call" arrangement exists for.
        return _Settlement("unknown")
    if call.outcome == str(ToolOutcomeKind.REFUSED):
        # The server answered no. `trading-mcp` refuses before touching the account for a
        # bad request, and turns a provider REJECTED into a refusal too; either way
        # nothing was placed. Its access-failure refusals are the exception, and they say
        # so in their own words.
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
    # The column refuses a non-positive size (`0004_trades.py`), and a model is free to
    # ask for one — dropped to NULL here rather than allowed to fail the insert, which
    # would cost the run a trace row over an argument `trading-mcp` is about to refuse
    # anyway.
    return parsed if key != "size" or parsed > 0 else None
