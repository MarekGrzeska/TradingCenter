"""One evaluation, and the loop that keeps asking for one. Only closed bars, because the archive answers with those
alone; a failure to see is recorded rather than swallowed, and nothing here has a client for an account at all."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime

from tc_runtime.liveness import LoopHeartbeat

from .. import resolver
from ..alerts import Alerts, is_new_setup
from ..archive import Archive
from ..errors import StrategyError
from ..gates import ReasonKind, apply, coverage, reward_over_risk
from ..spec import Decision
from ..store import (
    Watch,
    facts_snapshot,
    last_decision,
    list_watches,
    read_parameter_set,
    record_decision,
)

log = logging.getLogger(__name__)

# The platform's floor for reward over risk: a strategy may want more of itself, none may want less. Here rather than
# in settings because it is a property of what this platform calls a setup, not a knob to differ on.
MINIMUM_REWARD_OVER_RISK = 1.5


@dataclass(frozen=True)
class Evaluated:
    """What one pass over one watch came to — for the log, and for a test to read."""

    watch: Watch
    as_of: datetime | None
    decision: Decision | None
    reason_kind: ReasonKind | None = None
    recorded: bool = False
    # Whether the operator was told about this one. False covers three different things and
    # deliberately does not tell them apart: not a trade, not a change, or nobody to tell.
    announced: bool = False
    # Set when the pass could not get as far as a decision at all: no bars yet for this
    # pair, or a parameter set that has gone missing. Distinct from a decision to refuse.
    skipped: str | None = None


async def evaluate_once(
    pool, archive: Archive, watch: Watch, alerts: Alerts | None = None
) -> Evaluated:
    """One watch, one bar, one decision — or the reason there was not one. The watch's own revision, never
    the newest: a definition may have moved on three times without changing what this watch decides."""
    async with pool.acquire() as conn:
        try:
            found = await resolver.resolve_watch(conn, watch)
        except StrategyError as err:
            # A watch for a strategy this image no longer carries, or a revision it cannot read. Skipped rather than
            # raised: the other watches are unaffected, and the operator's remedy is a row, not a restart.
            return Evaluated(watch=watch, as_of=None, decision=None, skipped=str(err))
        parameters = await read_parameter_set(conn, watch.parameter_set_id)
    spec = found.spec
    if parameters is None:
        return Evaluated(
            watch=watch, as_of=None, decision=None, skipped="its parameter set is gone"
        )
    resolved = spec.resolve_params(parameters.params)

    try:
        as_of = await archive.last_closed_bar(watch.symbol, spec.resolution)
    except StrategyError as err:
        # Cannot even ask which bar it is. Nothing to record against — a decision needs a
        # bar to belong to — so this is a skip with a reason in the log.
        return Evaluated(watch=watch, as_of=None, decision=None, skipped=str(err))
    if as_of is None:
        return Evaluated(
            watch=watch, as_of=None, decision=None, skipped="the archive holds no closed bar yet"
        )

    async with pool.acquire() as conn:
        previous = await last_decision(conn, watch.strategy_id, watch.symbol)
    if previous is not None and previous.as_of >= as_of:
        # The commonest outcome by far: the loop wakes more often than bars close. One
        # cheap query and nothing else — no read of the archive, no evaluation.
        return Evaluated(watch=watch, as_of=as_of, decision=None, skipped="already decided")

    try:
        read = await archive.read_facts(spec, watch.symbol, resolved, as_of=as_of)
    except StrategyError as err:
        # Recorded, and this is the point: a strategy that could not see is not a strategy
        # that saw nothing, and the record has to say which it was.
        decision = Decision.no_trade(f"the facts could not be read: {err}")
        recorded = await _write(
            pool, watch, as_of, decision, "coverage", {"error": str(err)}, found.revision_id
        )
        return Evaluated(
            watch=watch, as_of=as_of, decision=decision, reason_kind="coverage", recorded=recorded
        )

    decision = spec.evaluate(read.facts, resolved)
    decision, reason_kind = apply(
        decision,
        [
            coverage(read.gaps),
            reward_over_risk(decision, MINIMUM_REWARD_OVER_RISK),
        ],
    )
    recorded = await _write(
        pool,
        watch,
        as_of,
        decision,
        reason_kind,
        facts_snapshot(read.facts, read.gaps),
        found.revision_id,
    )
    announced = False
    if recorded and alerts is not None and is_new_setup(decision, previous):
        announced = await _announce(pool, alerts, watch, decision)
    return Evaluated(
        watch=watch,
        as_of=as_of,
        decision=decision,
        reason_kind=reason_kind,
        recorded=recorded,
        announced=announced,
    )


async def _announce(pool, alerts: Alerts, watch: Watch, decision) -> bool:
    """The decision that was just written, told to the operator. Read back rather than returned by
    the write: the id is needed only on this path, which is a handful of bars a day."""
    async with pool.acquire() as conn:
        written = await last_decision(conn, watch.strategy_id, watch.symbol)
    if written is None:
        return False
    return await alerts.announce(
        pool,
        strategy_id=watch.strategy_id,
        symbol=watch.symbol,
        decision=decision,
        decision_id=written.id,
    )


async def _write(
    pool, watch: Watch, as_of, decision, reason_kind, facts, strategy_revision_id
) -> bool:
    async with pool.acquire() as conn:
        return await record_decision(
            conn,
            strategy_id=watch.strategy_id,
            symbol=watch.symbol,
            parameter_set_id=watch.parameter_set_id,
            as_of=as_of,
            decision=decision,
            reason_kind=reason_kind,
            facts=facts,
            strategy_revision_id=strategy_revision_id,
        )


async def evaluate_all(pool, archive: Archive, alerts: Alerts | None = None) -> list[Evaluated]:
    """Every active watch, one after another. Sequential on purpose: the archive counts its budget against
    the whole system, and bars close on the scale of minutes."""
    async with pool.acquire() as conn:
        watches = await list_watches(conn, active_only=True)

    results: list[Evaluated] = []
    for watch in watches:
        try:
            results.append(await evaluate_once(pool, archive, watch, alerts))
        except Exception:
            # One watch's unexpected failure must not stop the others: a platform that stops watching everything
            # because one strategy raised fails in the least useful way.
            log.exception(
                "evaluating %s on %s failed unexpectedly", watch.strategy_id, watch.symbol
            )
    return results


class EvaluationLoop:
    """The clock. Wakes, evaluates every active watch, sleeps. In the module's own process rather than a
    scheduler outside it: a rhythm that lives outside the thing it drives is a second place to be wrong."""

    def __init__(
        self,
        pool,
        archive: Archive,
        *,
        interval_seconds: int,
        alerts: Alerts | None = None,
        heartbeat: LoopHeartbeat | None = None,
    ) -> None:
        self._pool = pool
        self._archive = archive
        self._interval = interval_seconds
        # `None` where no gateway is configured, which is a supported state: the platform decides
        # either way, and being unable to say so is never a reason not to have decided.
        self._alerts = alerts
        # `None` in a test that drives a pass itself: what the loop reports is the loop's, and a
        # caller with no loop has nothing to report.
        self._heartbeat = heartbeat
        self._task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="strategy-evaluation-loop")

    async def aclose(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None

    async def _run(self) -> None:
        log.info("evaluation loop started, waking every %ds", self._interval)
        while True:
            try:
                await evaluate_all(self._pool, self._archive, self._alerts)
            except asyncio.CancelledError:
                raise
            except Exception:
                # The loop outlives any one failure: everything below it already handles its own, and this is the
                # backstop that keeps a surprise from ending the process's whole reason for running.
                log.exception("an evaluation pass failed")
            else:
                # After the pass and only after it: a pass that raised is a pass that did not happen, and a
                # heartbeat beaten regardless would report a stopped loop as healthy.
                if self._heartbeat is not None:
                    self._heartbeat.beat()
            await asyncio.sleep(self._interval)
