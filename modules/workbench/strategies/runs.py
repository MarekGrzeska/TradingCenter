"""A run as the operator asks for one, checked before it is queued, and the only door to the `runs` and `run_trades`
tables. A run is never deleted: every one, failed and cancelled included, is the count of what was tried."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

import asyncpg
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from tc_runtime.db import Conn, fetch_one

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
    costs: CostModel
    capital: float = Field(default=10_000.0, gt=0)
    seed: int = Field(default=1, ge=0)


def check_request(request: RunIn, declared: Mapping[str, Mapping[str, float]], max_minute_bars: int) -> list[Problem]:
    """Everything wrong with a run before it is queued. `declared` is the revision's `params` section."""
    problems: list[Problem] = []
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


def resolved_params(request: RunIn, declared: Mapping[str, Mapping[str, float]]) -> dict[str, float]:
    return {name: request.params.get(name, spec["default"]) for name, spec in declared.items()}


async def enqueue(conn: Conn, request: RunIn, revision: int, params: Mapping[str, float]) -> int:
    recorded = request.model_dump(mode="json", by_alias=True) | {"revision": revision, "params": dict(params)}
    row = await fetch_one(
        conn, "INSERT INTO runs (strategy_id, revision, request) VALUES ($1, $2, $3::jsonb) RETURNING id",
        request.strategy_id, revision, json.dumps(recorded),
    )
    return row["id"]


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
                "initial_stop", "result_r", "result_money", "costs", "exit_reason", "pessimistic",
            ],
            records=[
                (
                    run_id, seq, t["side"], moment(t["entry_time"]), t["entry_price"], moment(t["exit_time"]),
                    t["exit_price"], t["units"], t["initial_stop"], t["result_r"], t["result_money"],
                    json.dumps(t["costs"]), t["exit_reason"], t["pessimistic"],
                )
                for seq, t in enumerate(trades)
            ],
        )
        await conn.execute(
            "UPDATE runs SET status = 'done', finished_at = now(), engine_version = $2, report = $3::jsonb, "
            "provenance = $4::jsonb WHERE id = $1 AND status = 'running'",
            run_id, engine_version, json.dumps(report), json.dumps(provenance),
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
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    report: dict | None
    provenance: dict | None


def run_row(row: asyncpg.Record) -> RunRow:
    return RunRow(
        row["id"], row["strategy_id"], row["revision"], row["status"], row["reason"], row["engine_version"],
        decoded(row["request"]), row["queued_at"], row["started_at"], row["finished_at"], decoded(row["report"]),
        decoded(row["provenance"]),
    )


async def get_run(conn: Conn, run_id: int) -> RunRow | None:
    row = await conn.fetchrow("SELECT * FROM runs WHERE id = $1", run_id)
    return None if row is None else run_row(row)


async def status_of(conn: Conn, run_id: int) -> str | None:
    return await conn.fetchval("SELECT status FROM runs WHERE id = $1", run_id)



async def list_runs(conn: Conn, strategy_id: int | None, limit: int) -> list[RunRow]:
    rows = await conn.fetch(
        "SELECT * FROM runs WHERE ($1::bigint IS NULL OR strategy_id = $1) ORDER BY queued_at DESC, id DESC LIMIT $2",
        strategy_id, limit,
    )
    return [run_row(row) for row in rows]


async def trades_page(conn: Conn, run_id: int, offset: int, limit: int) -> tuple[int, list[asyncpg.Record]]:
    total = await conn.fetchval("SELECT count(*) FROM run_trades WHERE run_id = $1", run_id)
    rows = await conn.fetch(
        "SELECT * FROM run_trades WHERE run_id = $1 ORDER BY seq OFFSET $2 LIMIT $3", run_id, offset, limit
    )
    return int(total or 0), list(rows)


async def queued(conn: Conn) -> int:
    return int(await conn.fetchval("SELECT count(*) FROM runs WHERE status = 'queued'") or 0)
