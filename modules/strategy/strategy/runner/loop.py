"""One evaluation, and the loop that keeps asking for one.

The order inside an evaluation is deliberate and is the whole of what the runtime does:

    the last closed bar  ->  already decided?  ->  read the facts  ->  evaluate
                                                ->  the platform's gates  ->  record

**Only closed bars.** The archive's `/candles` answers with closed bars only, so asking it
what the last one is *is* the rule — this module needs no opinion of its own about when a
period ends, and a forming candle can never reach a strategy.

**A failure to see is recorded, not swallowed.** An archive that will not answer produces a
decision that says so, with its own reason kind, rather than a gap in the record. The
operator's question three weeks later is "why did nothing happen", and silence is the one
answer that cannot be given.

**Nothing here reaches an account.** There is no client for one in this module at all
(`strategy-runtime`, "Platforma nie ma drogi do konta").
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime

from .. import resolver
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

# The platform's floor for reward over risk. A strategy may want more of itself; none may
# want less. Here rather than in settings because it is a property of what this platform
# will call a setup, not a knob for an environment to differ on.
MINIMUM_REWARD_OVER_RISK = 1.5


@dataclass(frozen=True)
class Evaluated:
    """What one pass over one watch came to — for the log, and for a test to read."""

    watch: Watch
    as_of: datetime | None
    decision: Decision | None
    reason_kind: ReasonKind | None = None
    recorded: bool = False
    # Set when the pass could not get as far as a decision at all: no bars yet for this
    # pair, or a parameter set that has gone missing. Distinct from a decision to refuse.
    skipped: str | None = None


async def evaluate_once(pool, archive: Archive, watch: Watch) -> Evaluated:
    """One watch, one bar, one decision — or the reason there was not one.

    **The watch's own revision, never the newest.** A definition may have moved on three
    times since this watch was started; none of that changes what it decides until somebody
    points it at a newer one (`strategy-configurator`, "Rewizja jest niezmienna, a
    obserwacja ją przypina").
    """
    async with pool.acquire() as conn:
        try:
            found = await resolver.resolve_watch(conn, watch)
        except StrategyError as err:
            # A watch for a strategy this image no longer carries, or a revision it cannot
            # read. Skipped rather than raised: the other watches are unaffected, and the
            # operator's remedy is a row, not a restart.
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
    return Evaluated(
        watch=watch, as_of=as_of, decision=decision, reason_kind=reason_kind, recorded=recorded
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


async def evaluate_all(pool, archive: Archive) -> list[Evaluated]:
    """Every active watch, one after another.

    Sequential on purpose. The archive counts its budget against the whole system, and a
    platform that fanned out over twenty watches at once would be competing with the chart
    the operator is looking at right now. Bars close on the scale of minutes; there is
    nothing to be won by hurrying.
    """
    async with pool.acquire() as conn:
        watches = await list_watches(conn, active_only=True)

    results: list[Evaluated] = []
    for watch in watches:
        try:
            results.append(await evaluate_once(pool, archive, watch))
        except Exception:
            # One watch's unexpected failure must not stop the others: they are independent
            # by construction, and a platform that stops watching everything because one
            # strategy raised is a platform that fails in the least useful way.
            log.exception(
                "evaluating %s on %s failed unexpectedly", watch.strategy_id, watch.symbol
            )
    return results


class EvaluationLoop:
    """The clock. Wakes, evaluates every active watch, sleeps.

    In the module's own process rather than a scheduler outside it, for the reason the
    teams' clock gives: a rhythm that lives outside the thing it drives is a second place
    to deploy and a second place to be wrong about what is running.
    """

    def __init__(self, pool, archive: Archive, *, interval_seconds: int) -> None:
        self._pool = pool
        self._archive = archive
        self._interval = interval_seconds
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
                await evaluate_all(self._pool, self._archive)
            except asyncio.CancelledError:
                raise
            except Exception:
                # The loop outlives any one failure. Everything below it already handles
                # its own; this is the backstop that keeps a surprise from ending the
                # process's whole reason for running.
                log.exception("an evaluation pass failed")
            await asyncio.sleep(self._interval)
