"""Running a strategy from the conversation: queued like the operator's, counted like the operator's, made with the
instrument's cost profile — read off the broker the first time, never a number of the model's — and one at a time."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import AwareDatetime, BaseModel, Field, ValidationError

from .. import compare, runs, store
from ..archive import ArchiveUnavailable
from ..broker_costs import BrokerCostsMissing
from ..runs import RunIn
from ._shared import READ_ONLY, WRITES, ToolContext, refusal

# How long run_backtest waits for its run before answering with the id. An H1 strategy over a year with its random-entry
# benchmark takes about 2 s (measured for stage 1); a minute strategy can take minutes, and a turn should not.
WAIT_SECONDS = 20.0


class RunResult(BaseModel):
    run_id: int
    strategy_id: int
    revision: int
    status: str
    reason: str | None = None
    costs: dict[str, Any] = Field(description="the values the run is made with")
    costs_source: str = Field(description="`broker` or `operator` (the instrument's profile), or `none`")
    headline: dict[str, Any] | None = Field(default=None, description="present once the run is done")
    next_step: str


class RunRead(BaseModel):
    run_id: int
    strategy_id: int
    revision: int
    status: str
    reason: str | None
    requested_by: str
    request: dict[str, Any] = Field(description="range, parameters, costs, capital and seed the run was made with")
    engine_version: int | None
    report: dict[str, Any] | None = Field(description="every metric and benchmark; the daily curve is left out")
    provenance: dict[str, Any] | None = Field(description="the revision's hash, and the stretches the archive never verified")


class Comparison(BaseModel):
    runs: list[dict[str, Any]]
    note: str = "Same range, costs and engine. Numbers only — which one is better is the operator's call."


def _headline(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if report is None:
        return None
    keys = ("trades", "total_r", "expectancy_r", "win_rate", "profit_factor", "max_drawdown_r", "sharpe")
    return {key: report.get(key) for key in keys}


def register(mcp: FastMCP, ctx: ToolContext) -> None:
    @mcp.tool(annotations=WRITES)
    async def run_backtest(
        strategy_id: int,
        start: AwareDatetime,
        end: AwareDatetime,
        revision: int | None = None,
        params: dict[str, float] | None = None,
        capital: float = 10_000.0,
        seed: int = 1,
        without_costs: bool = False,
    ) -> RunResult:
        """Backtests a strategy over [start, end) (UTC), with its instrument's cost profile — read off the broker if it
        has none; say which costs were used. Use it when the operator asks for a run. Every run is a trial counted
        against the strategy, so do not run variants of the parameters to look for a better result.

        `without_costs` only when the operator asks for a run without costs in so many words: its result leaves out
        spread, slippage and financing.

        Waits up to 20 s for the result and answers with its main numbers; a longer run answers with its id, for
        read_run later. Only one run you asked for may wait at a time."""
        pool = ctx.state.pool
        async with pool.acquire() as conn:
            waiting = await runs.waiting_for_agent(conn)
            if waiting is not None:
                raise refusal(f"run {waiting}, which you asked for, has not finished; read it with read_run first")
            try:
                found = await store.get_revision(conn, strategy_id, revision)
            except store.NotFound:
                raise refusal(f"strategy {strategy_id} has no revision {revision or ''}".strip()) from None
            try:
                request = RunIn.model_validate({
                    "strategy_id": strategy_id, "revision": found.n, "from": start, "to": end,
                    "params": params or {}, "without_costs": without_costs, "capital": capital, "seed": seed,
                })
            except ValidationError as err:
                raise refusal(f"the run cannot be queued: {err.errors()[0]['msg']}") from None
            declared = found.document.get("params", {})
            problems = runs.check_request(request, declared, ctx.state.settings.max_minute_bars)
            if problems:
                raise refusal("the run cannot be queued", problems)
            try:
                costs = await runs.resolved_costs(conn, ctx.state.archive, request, found.document["symbol"])
            except (BrokerCostsMissing, ArchiveUnavailable) as err:
                raise refusal(f"the broker's costs cannot be read, and a run is never made without them: {err}; "
                              "nothing was queued") from None
            run_id = await runs.enqueue(
                conn, request, found.n, runs.resolved_params(request, declared), costs, "agent"
            )
        queue = ctx.state.queue
        queue.listen(run_id)
        queue.wake()
        await queue.wait_for(run_id, WAIT_SECONDS)
        async with pool.acquire() as conn:
            row = await runs.get_run(conn, run_id)
        assert row is not None
        done = row.status == "done"
        return RunResult(
            run_id=run_id, strategy_id=strategy_id, revision=found.n, status=row.status, reason=row.reason,
            costs=costs.costs.model_dump(mode="json"), costs_source=costs.source, headline=_headline(row.report),
            next_step="read_run gives every number" if done else "still computing; read_run tells when it is done",
        )

    @mcp.tool(annotations=READ_ONLY)
    async def read_run(run_id: int) -> RunRead:
        """One run: its status, what it was made with, every metric and benchmark of its report, and where the data was
        not verified. The trades and the daily curve are on the Strategies tab."""
        async with ctx.state.pool.acquire() as conn:
            row = await runs.get_run(conn, run_id)
        if row is None:
            raise refusal(f"run {run_id} does not exist")
        report = None if row.report is None else {k: v for k, v in row.report.items() if k != "equity"}
        provenance = None if row.provenance is None else {
            k: row.provenance.get(k) for k in ("content_hash", "engine_version", "uncovered", "unsettled")
        }
        return RunRead(
            run_id=row.id, strategy_id=row.strategy_id, revision=row.revision, status=row.status, reason=row.reason,
            requested_by=row.requested_by, request=row.request, engine_version=row.engine_version, report=report,
            provenance=provenance,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def compare_runs(run_ids: list[int]) -> Comparison:
        """Two to five finished runs side by side — refused, with every difference named, unless they share the range,
        the costs and the engine version, because then the numbers would not measure the same thing."""
        if (problem := compare.count_problem(run_ids)) is not None:
            raise refusal(problem)
        async with ctx.state.pool.acquire() as conn:
            rows = [await runs.get_run(conn, run_id) for run_id in run_ids]
        missing = [run_id for run_id, row in zip(run_ids, rows, strict=True) if row is None]
        if missing:
            raise refusal(f"no such run: {', '.join(map(str, missing))}")
        try:
            return Comparison(runs=compare.compare([row for row in rows if row is not None]))
        except compare.NotComparable as err:
            raise refusal("these runs cannot be compared: " + "; ".join(err.reasons)) from None

