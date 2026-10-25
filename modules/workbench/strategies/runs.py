"""A run as the operator asks for one, checked before it is queued, and the only door to the `runs` and `run_trades`
tables. A run is never deleted: every one, failed and cancelled included, is the count of what was tried."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

import asyncpg
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from tc_runtime.db import Conn, fetch_one

from . import costs_store, margins
from .archive import Archive
from .costs import CostModel
from .problems import Problem
from .reading import minute_bars
from .series import epoch, moment
from .store import decoded


class RunIn(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, populate_by_name=True)

    strategy_id: int
    # The latest revision when left out; recorded as the number it was, never as "latest".
    revision: int | None = Field(default=None, ge=1)
    from_: AwareDatetime = Field(alias="from")
    to: AwareDatetime
    params: dict[str, float] = Field(default_factory=dict)
    # Left out, the instrument's profile — read off the broker when there is none yet.
    costs: CostModel | None = None
    # A choice, not a model of zeros: the report says the result leaves out spread, slippage and financing (design D4).
    without_costs: bool = False
    capital: float = Field(default=10_000.0, gt=0)
    seed: int = Field(default=1, ge=0)


def check_request(request: RunIn, declared: Mapping[str, Mapping[str, float]], max_minute_bars: int) -> list[Problem]:
    """Everything wrong with a run before it is queued. `declared` is the revision's `params` section."""
    problems: list[Problem] = []
    if request.costs is not None and request.without_costs:
        problems.append(Problem(
            "without_costs", "a run is made either with these costs or without costs, not both",
            hint="leave out `costs`, or `without_costs`",
        ))
    start, end = epoch(request.from_), epoch(request.to)
    if end <= start:
        problems.append(Problem("to", "a run's range ends after it starts"))
    bars = minute_bars(start, end)
    if bars > max_minute_bars:
        problems.append(Problem(
            "to", f"this range can hold {bars} minute candles of the traded instrument; one run reads at most "
            f"{max_minute_bars}", hint="shorten the range, or split it into runs",
        ))
    for name, value in request.params.items():
        spec = declared.get(name)
        if spec is None:
            problems.append(Problem(f"params.{name}", f"`{name}` is not a parameter of this revision"))
        elif not spec["min"] <= value <= spec["max"]:
            problems.append(Problem(
                f"params.{name}", f"{value:g} is outside the declared {spec['min']:g} to {spec['max']:g}",
            ))
    return problems


CostsSource = Literal["request", "broker", "operator", "none"]
NO_COSTS = CostModel(spread=0.0, slippage=0.0, overnight_long=0.0, overnight_short=0.0, rollover_hour=0)


@dataclass(frozen=True)
class RunCosts:
    costs: CostModel
    source: CostsSource
    # When the broker's profile was read; null for any other source.
    fetched_at: datetime | None = None

    def recorded(self) -> dict[str, Any]:
        return {
            "costs": self.costs.model_dump(mode="json"), "costs_source": self.source,
            "costs_fetched_at": None if self.fetched_at is None else self.fetched_at.isoformat(),
        }


async def resolved_costs(conn: Conn, archive: Archive, request: RunIn, symbol: str) -> RunCosts:
    """The request's costs, else the instrument's profile, else none when that was asked for. Raises what
    `costs_store.get_or_fetch` raises when the broker cannot give a profile."""
    if request.without_costs:
        return RunCosts(NO_COSTS, "none")
    if request.costs is not None:
        return RunCosts(request.costs, "request")
    profile = await costs_store.get_or_fetch(conn, archive, symbol)
    return RunCosts(profile.costs, profile.source, profile.fetched_at)


def costs_source_of(request: Mapping[str, Any], requested_by: str) -> CostsSource:
    """A run recorded before the source was: the operator's came with costs, the agent's from the operator's profile."""
    recorded = request.get("costs_source")
    if recorded is not None:
        return recorded
    return "operator" if requested_by == "agent" else "request"


def costs_marks(request: Mapping[str, Any], requested_by: str) -> dict[str, Any]:
    """What a report and a list say about a run's costs and deposit — read off its `request`, where they were recorded."""
    return {
        "costs_source": costs_source_of(request, requested_by),
        "costs_fetched_at": request.get("costs_fetched_at"),
        "without_costs": bool(request.get("without_costs", False)),
        "margin_factor": request.get("margin_factor"),
    }


async def resolved_margin(conn: Conn, archive: Archive, document: Mapping[str, Any]) -> float | None:
    """The instrument's deposit when the document is sized by it, else none — no other run reads it. Raises what
    `margins.get_or_fetch` raises."""
    if document.get("sizing", {}).get("mode") != "margin_fraction":
        return None
    return (await margins.get_or_fetch(conn, archive, document["symbol"])).margin_factor


def resolved_params(request: RunIn, declared: Mapping[str, Mapping[str, float]]) -> dict[str, float]:
    return {name: request.params.get(name, spec["default"]) for name, spec in declared.items()}


async def enqueue(
    conn: Conn, request: RunIn, revision: int, params: Mapping[str, float], costs: RunCosts,
    requested_by: str = "operator", margin_factor: float | None = None,
) -> int:
    """The values the run is made with, never a reference to the profile they came from."""
    recorded = request.model_dump(mode="json", by_alias=True) | {
        "revision": revision, "params": dict(params), **costs.recorded(), "margin_factor": margin_factor,
    }
    row = await fetch_one(
        conn,
        "INSERT INTO runs (strategy_id, revision, request, requested_by) VALUES ($1, $2, $3::jsonb, $4) RETURNING id",
        request.strategy_id, revision, json.dumps(recorded), requested_by,
    )
    return row["id"]


async def waiting_for_agent(conn: Conn) -> int | None:
    """A run the agent asked for that is still queued or computing — the agent waits for it before asking again."""
    return await conn.fetchval(
        "SELECT id FROM runs WHERE status IN ('queued', 'running') AND requested_by = 'agent' ORDER BY id LIMIT 1"
    )


async def interrupted_by_restart(conn: Conn) -> int:
    """At start: whatever was computing when the process stopped did not finish, and says so."""
    result = await conn.execute(
        "UPDATE runs SET status = 'failed', reason = 'interrupted by a restart', finished_at = now() "
        "WHERE status = 'running'"
    )
    return int(result.split()[-1])


async def claim(conn: Conn) -> asyncpg.Record | None:
    """The oldest queued run, now running. `SKIP LOCKED` so two processes never take the same one."""
    return await conn.fetchrow(
        """
        UPDATE runs SET status = 'running', started_at = now()
        WHERE id = (SELECT id FROM runs WHERE status = 'queued' ORDER BY queued_at, id LIMIT 1 FOR UPDATE SKIP LOCKED)
        RETURNING id, strategy_id, revision, request
        """
    )


async def finish(
    pool: asyncpg.Pool, run_id: int, engine_version: int, report: dict, provenance: dict, trades: list[dict]
) -> None:
    async with pool.acquire() as conn, conn.transaction():
        # Still running, held for the transaction: a run cancelled while its worker was answering keeps no trades.
        status = await conn.fetchval("SELECT status FROM runs WHERE id = $1 FOR UPDATE", run_id)
        if status != "running":
            return
        await conn.copy_records_to_table(
            "run_trades",
            columns=[
                "run_id", "seq", "side", "entry_time", "entry_price", "exit_time", "exit_price", "units",
                "initial_stop", "result_r", "result_money", "result_pct", "mae_pct", "costs", "exit_reason",
                "pessimistic",
            ],
            records=[
                (
                    run_id, seq, t["side"], moment(t["entry_time"]), t["entry_price"], moment(t["exit_time"]),
                    t["exit_price"], t["units"], t["initial_stop"], t["result_r"], t["result_money"],
                    t["result_pct"], t["mae_pct"], json.dumps(t["costs"]), t["exit_reason"], t["pessimistic"],
                )
                for seq, t in enumerate(trades)
            ],
        )
        await conn.execute(
            "UPDATE runs SET status = 'done', finished_at = now(), engine_version = $2, report = $3::jsonb, "
            "provenance = $4::jsonb, headline = $5::jsonb WHERE id = $1 AND status = 'running'",
            run_id, engine_version, json.dumps(report), json.dumps(provenance),
            json.dumps({key: report.get(key) for key in HEADLINE}),
        )


async def fail(conn: Conn, run_id: int, reason: str, status: str = "failed") -> None:
    await conn.execute(
        "UPDATE runs SET status = $3, reason = $2, finished_at = now() WHERE id = $1 AND status IN ('queued', 'running')",
        run_id, reason, status,
    )


async def cancel(conn: Conn, run_id: int) -> str | None:
    """Cancels a queued run at once; a running one is marked here and stopped by the queue. The status it was in, or
    `None` when there is no such run."""
    row = await conn.fetchrow("SELECT status FROM runs WHERE id = $1", run_id)
    if row is None:
        return None
    if row["status"] in ("queued", "running"):
        await fail(conn, run_id, "cancelled by the operator", status="cancelled")
    return row["status"]


@dataclass(frozen=True)
class RunRow:
    id: int
    strategy_id: int
    revision: int
    status: str
    reason: str | None
    engine_version: int | None
    request: dict
    requested_by: str
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    report: dict | None
    provenance: dict | None


def run_row(row: asyncpg.Record) -> RunRow:
    return RunRow(
        row["id"], row["strategy_id"], row["revision"], row["status"], row["reason"], row["engine_version"],
        decoded(row["request"]), row["requested_by"], row["queued_at"], row["started_at"], row["finished_at"],
        decoded(row["report"]), decoded(row["provenance"]),
    )


async def get_run(conn: Conn, run_id: int) -> RunRow | None:
    row = await conn.fetchrow("SELECT * FROM runs WHERE id = $1", run_id)
    return None if row is None else run_row(row)


async def status_of(conn: Conn, run_id: int) -> str | None:
    return await conn.fetchval("SELECT status FROM runs WHERE id = $1", run_id)



# A list carries no report or provenance — those are megabytes across a page, and `GET /runs/{id}` has them. The headline
# is its own column, written with the report, so polling a list never detoasts a report and its curve.
_LIST = """
    SELECT id, strategy_id, revision, status, reason, engine_version, request, requested_by, queued_at, started_at,
           finished_at, headline
"""

HEADLINE = ("trades", "total_r", "expectancy_r", "max_drawdown_r", "sharpe", "return_pct")


async def list_runs(conn: Conn, strategy_id: int | None, offset: int, limit: int) -> list[asyncpg.Record]:
    # Two statements rather than `$1 IS NULL OR …`: a cached generic plan of that form cannot use runs_by_strategy.
    if strategy_id is None:
        return list(await conn.fetch(
            f"{_LIST} FROM runs ORDER BY queued_at DESC, id DESC OFFSET $1 LIMIT $2", offset, limit
        ))
    return list(await conn.fetch(
        f"{_LIST} FROM runs WHERE strategy_id = $1 ORDER BY queued_at DESC, id DESC OFFSET $2 LIMIT $3",
        strategy_id, offset, limit,
    ))


async def trades_page(conn: Conn, run_id: int, offset: int, limit: int) -> tuple[int, list[asyncpg.Record]]:
    total = await conn.fetchval("SELECT count(*) FROM run_trades WHERE run_id = $1", run_id)
    rows = await conn.fetch(
        "SELECT * FROM run_trades WHERE run_id = $1 ORDER BY seq OFFSET $2 LIMIT $3", run_id, offset, limit
    )
    return int(total or 0), list(rows)


async def queued(conn: Conn) -> int:
    return int(await conn.fetchval("SELECT count(*) FROM runs WHERE status = 'queued'") or 0)
