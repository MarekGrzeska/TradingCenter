"""The only door to this module's three tables.

One place that writes, so the rules the schema states are stated once in Python too. Two
of them are worth reading before changing anything:

**Parameter sets are append-only.** Nothing updates one. A decision names the version it
was computed under, and answering "what was this decided with" a month later requires that
version to still read the way it read then — so a change of mind is the next version, and
the old one stays.

**A decision is keyed by its bar.** `ON CONFLICT DO NOTHING` on (strategy, symbol, as_of)
is what makes the loop idempotent: it re-reads the last closed bar on every wake and after
every restart, and writing a second row for that bar would turn a restart into a second
setup.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import asyncpg

from .gates import ReasonKind
from .spec import Candle, Decision, Facts, FactValue, Level, Marker, Zone


@dataclass(frozen=True)
class ParameterSet:
    id: int
    strategy_id: str
    version: int
    params: dict[str, float]
    created_at: datetime


@dataclass(frozen=True)
class Watch:
    id: int
    strategy_id: str
    symbol: str
    parameter_set_id: int
    active: bool
    created_at: datetime


@dataclass(frozen=True)
class RecordedDecision:
    """A decision as it was written down — the strategy's answer plus its provenance."""

    id: int
    strategy_id: str
    symbol: str
    parameter_set_id: int
    as_of: datetime
    decision: Decision
    reason_kind: ReasonKind | None
    facts: dict[str, Any]
    created_at: datetime


# --- parameter sets -------------------------------------------------------------------


async def add_parameter_set(
    conn: asyncpg.Connection, strategy_id: str, params: Mapping[str, float]
) -> ParameterSet:
    """The next version for this strategy, whatever the last one was.

    The version is chosen inside the statement rather than read and then written: two
    requests arriving together would otherwise both read the same last version and one
    would lose on the unique constraint — which is the right outcome but a needlessly
    confusing way to reach it.
    """
    row = await conn.fetchrow(
        """
        INSERT INTO parameter_sets (strategy_id, version, params)
        VALUES (
            $1,
            coalesce((SELECT max(version) FROM parameter_sets WHERE strategy_id = $1), 0) + 1,
            $2::jsonb
        )
        RETURNING id, strategy_id, version, params, created_at
        """,
        strategy_id,
        json.dumps(dict(params)),
    )
    assert row is not None  # an INSERT ... RETURNING that inserted cannot answer nothing
    return _parameter_set(row)


async def read_parameter_set(conn: asyncpg.Connection, parameter_set_id: int) -> ParameterSet | None:
    row = await conn.fetchrow(
        "SELECT id, strategy_id, version, params, created_at FROM parameter_sets WHERE id = $1",
        parameter_set_id,
    )
    return _parameter_set(row) if row else None


async def list_parameter_sets(
    conn: asyncpg.Connection, strategy_id: str | None = None
) -> list[ParameterSet]:
    rows = await conn.fetch(
        """
        SELECT id, strategy_id, version, params, created_at
        FROM parameter_sets
        WHERE ($1::text IS NULL OR strategy_id = $1)
        ORDER BY strategy_id, version DESC
        """,
        strategy_id,
    )
    return [_parameter_set(row) for row in rows]


# --- watches --------------------------------------------------------------------------


async def put_watch(
    conn: asyncpg.Connection, strategy_id: str, symbol: str, parameter_set_id: int
) -> Watch:
    """Start watching a pair with a strategy, or point an existing watch at new parameters.

    Upsert rather than insert-or-refuse: "watch US100 with these parameters" is the whole
    of the operator's intent, and whether a row already existed is this module's business.
    A watch that had been deactivated comes back active — asking for it again is asking
    for it to run.
    """
    row = await conn.fetchrow(
        """
        INSERT INTO watches (strategy_id, symbol, parameter_set_id, active)
        VALUES ($1, $2, $3, true)
        ON CONFLICT (strategy_id, symbol) DO UPDATE
            SET parameter_set_id = excluded.parameter_set_id, active = true
        RETURNING id, strategy_id, symbol, parameter_set_id, active, created_at
        """,
        strategy_id,
        symbol,
        parameter_set_id,
    )
    assert row is not None
    return _watch(row)


async def set_watch_active(conn: asyncpg.Connection, watch_id: int, active: bool) -> Watch | None:
    row = await conn.fetchrow(
        """
        UPDATE watches SET active = $2 WHERE id = $1
        RETURNING id, strategy_id, symbol, parameter_set_id, active, created_at
        """,
        watch_id,
        active,
    )
    return _watch(row) if row else None


async def list_watches(conn: asyncpg.Connection, *, active_only: bool = False) -> list[Watch]:
    rows = await conn.fetch(
        """
        SELECT id, strategy_id, symbol, parameter_set_id, active, created_at
        FROM watches
        WHERE (NOT $1::boolean OR active)
        ORDER BY strategy_id, symbol
        """,
        active_only,
    )
    return [_watch(row) for row in rows]


# --- decisions ------------------------------------------------------------------------


async def record_decision(
    conn: asyncpg.Connection,
    *,
    strategy_id: str,
    symbol: str,
    parameter_set_id: int,
    as_of: datetime,
    decision: Decision,
    reason_kind: ReasonKind | None,
    facts: Mapping[str, Any],
) -> bool:
    """Write one decision. `False` when this bar already had one.

    The bar is the key, so this is safe to call again for a bar already decided — which the
    loop does on every wake, and every restart does for the bar it comes up on.
    """
    written = await conn.fetchval(
        """
        INSERT INTO decisions (
            strategy_id, symbol, parameter_set_id, as_of, action, reason, reason_kind,
            direction, entry, stop, target, rr, score, features, facts
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14::jsonb, $15::jsonb)
        ON CONFLICT (strategy_id, symbol, as_of) DO NOTHING
        RETURNING id
        """,
        strategy_id,
        symbol,
        parameter_set_id,
        as_of,
        decision.action,
        decision.reason,
        reason_kind if decision.action == "no_trade" else None,
        decision.direction,
        decision.entry,
        decision.stop,
        decision.target,
        decision.rr,
        decision.score,
        json.dumps(dict(decision.features)),
        json.dumps(dict(facts)),
    )
    return written is not None


async def last_decision(
    conn: asyncpg.Connection, strategy_id: str, symbol: str
) -> RecordedDecision | None:
    row = await conn.fetchrow(
        f"SELECT {_DECISION_COLUMNS} FROM decisions WHERE strategy_id = $1 AND symbol = $2 "
        "ORDER BY as_of DESC LIMIT 1",
        strategy_id,
        symbol,
    )
    return _decision(row) if row else None


async def read_decision(conn: asyncpg.Connection, decision_id: int) -> RecordedDecision | None:
    row = await conn.fetchrow(
        f"SELECT {_DECISION_COLUMNS} FROM decisions WHERE id = $1", decision_id
    )
    return _decision(row) if row else None


async def list_decisions(
    conn: asyncpg.Connection,
    *,
    strategy_id: str | None = None,
    symbol: str | None = None,
    action: str | None = None,
    limit: int = 100,
) -> list[RecordedDecision]:
    rows = await conn.fetch(
        f"""
        SELECT {_DECISION_COLUMNS} FROM decisions
        WHERE ($1::text IS NULL OR strategy_id = $1)
          AND ($2::text IS NULL OR symbol = $2)
          AND ($3::text IS NULL OR action = $3)
        ORDER BY as_of DESC, id DESC
        LIMIT $4
        """,
        strategy_id,
        symbol,
        action,
        limit,
    )
    return [_decision(row) for row in rows]


async def count_pending_setups(
    conn: asyncpg.Connection, strategy_id: str, *, since: datetime | None = None
) -> int:
    """How many bars this strategy last answered `trade` on — the number a trigger reads.

    Counted from the recorded decisions rather than kept as a running total, so the value a
    trigger compares against a threshold is the very same fact the woken team will read
    (`strategy-tools`).
    """
    return int(
        await conn.fetchval(
            """
            SELECT count(*) FROM decisions
            WHERE strategy_id = $1 AND action = 'trade'
              AND ($2::timestamptz IS NULL OR as_of >= $2)
            """,
            strategy_id,
            since,
        )
        or 0
    )


# --- backtest runs --------------------------------------------------------------------


@dataclass(frozen=True)
class BacktestRun:
    id: int
    strategy_id: str
    symbol: str
    resolution: str
    range_from: datetime
    range_to: datetime
    params: dict[str, float]
    costs: dict[str, float]
    report: dict[str, Any]
    ran_at: datetime


async def record_backtest_run(
    conn: asyncpg.Connection,
    *,
    strategy_id: str,
    symbol: str,
    resolution: str,
    range_from: datetime,
    range_to: datetime,
    params: Mapping[str, float],
    costs: Mapping[str, float],
    report: Mapping[str, Any],
) -> BacktestRun:
    """Keep a report whole. Runs are never updated — a rerun is another row, and comparing
    a strategy against its own earlier self is a thing an operator should be able to do."""
    row = await conn.fetchrow(
        f"""
        INSERT INTO backtest_runs (
            strategy_id, symbol, resolution, range_from, range_to, params, costs, report
        )
        VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8::jsonb)
        RETURNING {_RUN_COLUMNS}
        """,
        strategy_id,
        symbol,
        resolution,
        range_from,
        range_to,
        json.dumps(dict(params)),
        json.dumps(dict(costs)),
        json.dumps(dict(report)),
    )
    assert row is not None
    return _run(row)


async def list_backtest_runs(
    conn: asyncpg.Connection, *, strategy_id: str | None = None, limit: int = 50
) -> list[BacktestRun]:
    rows = await conn.fetch(
        f"""
        SELECT {_RUN_COLUMNS} FROM backtest_runs
        WHERE ($1::text IS NULL OR strategy_id = $1)
        ORDER BY ran_at DESC, id DESC
        LIMIT $2
        """,
        strategy_id,
        limit,
    )
    return [_run(row) for row in rows]


async def read_backtest_run(conn: asyncpg.Connection, run_id: int) -> BacktestRun | None:
    row = await conn.fetchrow(f"SELECT {_RUN_COLUMNS} FROM backtest_runs WHERE id = $1", run_id)
    return _run(row) if row else None


# --- rows to objects ------------------------------------------------------------------

_RUN_COLUMNS = (
    "id, strategy_id, symbol, resolution, range_from, range_to, params, costs, report, ran_at"
)


def _run(row: asyncpg.Record) -> BacktestRun:
    return BacktestRun(
        id=row["id"],
        strategy_id=row["strategy_id"],
        symbol=row["symbol"],
        resolution=row["resolution"],
        range_from=row["range_from"],
        range_to=row["range_to"],
        params=_json(row["params"]),
        costs=_json(row["costs"]),
        report=_json(row["report"]),
        ran_at=row["ran_at"],
    )



_DECISION_COLUMNS = (
    "id, strategy_id, symbol, parameter_set_id, as_of, action, reason, reason_kind, "
    "direction, entry, stop, target, rr, score, features, facts, created_at"
)


def _json(value: Any) -> Any:
    """asyncpg hands JSONB back as text unless a codec is registered; both are accepted so
    a caller that registered one is not broken by a helper that assumed otherwise."""
    return json.loads(value) if isinstance(value, str | bytes) else value


def _parameter_set(row: asyncpg.Record) -> ParameterSet:
    return ParameterSet(
        id=row["id"],
        strategy_id=row["strategy_id"],
        version=row["version"],
        params=_json(row["params"]),
        created_at=row["created_at"],
    )


def _watch(row: asyncpg.Record) -> Watch:
    return Watch(
        id=row["id"],
        strategy_id=row["strategy_id"],
        symbol=row["symbol"],
        parameter_set_id=row["parameter_set_id"],
        active=row["active"],
        created_at=row["created_at"],
    )


def _decision(row: asyncpg.Record) -> RecordedDecision:
    return RecordedDecision(
        id=row["id"],
        strategy_id=row["strategy_id"],
        symbol=row["symbol"],
        parameter_set_id=row["parameter_set_id"],
        as_of=row["as_of"],
        decision=Decision(
            action=row["action"],
            reason=row["reason"],
            direction=row["direction"],
            entry=row["entry"],
            stop=row["stop"],
            target=row["target"],
            rr=row["rr"],
            score=row["score"],
            features=_json(row["features"]),
        ),
        reason_kind=row["reason_kind"],
        facts=_json(row["facts"]),
        created_at=row["created_at"],
    )


def facts_snapshot(facts: Any, gaps: Sequence[Any] = ()) -> dict[str, Any]:
    """The facts an evaluation stood on, as JSON that can be read back into `Facts`.

    Kept in full rather than as a pointer at the archive: replay has to survive the
    archive's retention and any later correction to it (design.md, decision 4). What is
    stored is indicator output — lines, markers, zones — not raw candles beyond the ones
    the strategy was handed, so the size is bounded by what the strategy asked for.
    """
    return {
        "symbol": facts.symbol,
        "as_of": facts.as_of.isoformat(),
        "candles": [
            {
                "time": candle.time.isoformat(),
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
            }
            for candle in facts.candles
        ],
        "values": {
            key: {
                "key": value.key,
                "resolution": value.resolution,
                "times": [stamp.isoformat() for stamp in value.times],
                "lines": {name: list(values) for name, values in value.lines.items()},
                "markers": [
                    {"time": marker.time.isoformat(), "label": marker.label, "price": marker.price}
                    for marker in value.markers
                ],
                "zones": [
                    {
                        "from": zone.start.isoformat(),
                        "to": None if zone.end is None else zone.end.isoformat(),
                        "top": zone.top,
                        "bottom": zone.bottom,
                        "direction": zone.direction,
                        "touched_at": None
                        if zone.touched_at is None
                        else zone.touched_at.isoformat(),
                        "filled_at": None
                        if zone.filled_at is None
                        else zone.filled_at.isoformat(),
                    }
                    for zone in value.zones
                ],
                "levels": [
                    {
                        "from": level.time.isoformat(),
                        "price": level.price,
                        "label": level.label,
                        "count": level.count,
                    }
                    for level in value.levels
                ],
                "error": value.error,
            }
            for key, value in facts.values.items()
        },
        "gaps": [{"from": gap.start.isoformat(), "to": gap.end.isoformat()} for gap in gaps],
    }


def facts_from_snapshot(snapshot: Mapping[str, Any]) -> Facts:
    """The inverse of `facts_snapshot`, and the reason it is written in full.

    A recorded decision is evidence only if it can be re-decided. This is what makes that
    possible without asking the archive anything — the same readings go back into the same
    `evaluate`, and the answer either matches what was written down or something is wrong
    that nobody would otherwise have found (`strategy-runtime`).
    """
    return Facts(
        symbol=str(snapshot["symbol"]),
        as_of=datetime.fromisoformat(str(snapshot["as_of"])),
        candles=tuple(
            Candle(
                time=datetime.fromisoformat(str(row["time"])),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
            )
            for row in snapshot.get("candles", [])
        ),
        values={
            key: FactValue(
                key=str(value["key"]),
                resolution=str(value["resolution"]),
                times=tuple(datetime.fromisoformat(str(s)) for s in value.get("times", [])),
                lines={
                    name: tuple(None if v is None else float(v) for v in values)
                    for name, values in (value.get("lines") or {}).items()
                },
                markers=tuple(
                    Marker(
                        time=datetime.fromisoformat(str(row["time"])),
                        label=str(row["label"]),
                        price=None if row.get("price") is None else float(row["price"]),
                    )
                    for row in value.get("markers", [])
                ),
                zones=tuple(
                    Zone(
                        start=datetime.fromisoformat(str(row["from"])),
                        end=None if row.get("to") is None else datetime.fromisoformat(str(row["to"])),
                        top=float(row["top"]),
                        bottom=float(row["bottom"]),
                        direction=row.get("direction"),
                        touched_at=None
                        if row.get("touched_at") is None
                        else datetime.fromisoformat(str(row["touched_at"])),
                        filled_at=None
                        if row.get("filled_at") is None
                        else datetime.fromisoformat(str(row["filled_at"])),
                    )
                    for row in value.get("zones", [])
                ),
                levels=tuple(
                    Level(
                        time=datetime.fromisoformat(str(row["from"])),
                        price=float(row["price"]),
                        label=row.get("label"),
                        count=row.get("count"),
                    )
                    for row in value.get("levels", [])
                ),
                error=value.get("error"),
            )
            for key, value in (snapshot.get("values") or {}).items()
        },
    )
