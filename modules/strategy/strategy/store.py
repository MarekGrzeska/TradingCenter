"""The only door to this module's tables. Three rules the schema states are stated once here too:
parameter sets are append-only, a decision is keyed by its bar (`ON CONFLICT DO NOTHING`, which is what
makes the loop idempotent across a restart), and revisions are append-only for the same reason one layer up."""

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
class StrategyDefinition:
    """A clicked-together strategy, without its rule — the rule lives in its revisions."""

    id: int
    strategy_id: str
    name: str
    description: str
    latest_version: int
    created_at: datetime


@dataclass(frozen=True)
class StrategyRevision:
    """One immutable brushstroke of a definition: the whole rule, as it was written."""

    id: int
    definition_id: int
    strategy_id: str
    version: int
    definition: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True)
class ParameterSet:
    id: int
    strategy_id: str
    version: int
    params: dict[str, float]
    created_at: datetime
    # Which revision's declaration these values were checked against. `None` for a coded
    # entry, whose declaration is in the image and has no row to point at.
    strategy_revision_id: int | None = None


@dataclass(frozen=True)
class Watch:
    id: int
    strategy_id: str
    symbol: str
    parameter_set_id: int
    active: bool
    created_at: datetime
    # Pinned, never followed. Saving a newer revision leaves this one computing what it
    # was started with, and moving it is a separate act by the operator.
    strategy_revision_id: int | None = None


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
    strategy_revision_id: int | None = None
    # The revision's own number, joined in so a reader never has to resolve a surrogate id
    # to answer "which rule was this". `None` for a decision made by a coded entry.
    strategy_revision: int | None = None



async def add_definition(
    conn: asyncpg.Connection,
    *,
    strategy_id: str,
    name: str,
    description: str,
    definition: Mapping[str, Any],
) -> tuple[StrategyDefinition, StrategyRevision]:
    """A new clicked strategy and its first revision, in one transaction.

    One act rather than two, because a definition with no revision is a name with no rule —
    a state nothing downstream knows how to read and nobody meant to create.
    """
    async with conn.transaction():
        row = await conn.fetchrow(
            """
            INSERT INTO strategy_definitions (strategy_id, name, description)
            VALUES ($1, $2, $3)
            RETURNING id, strategy_id, name, description, created_at
            """,
            strategy_id,
            name,
            description,
        )
        assert row is not None
        revision = await _insert_revision(conn, row["id"], strategy_id, definition)
    return (
        StrategyDefinition(
            id=row["id"],
            strategy_id=row["strategy_id"],
            name=row["name"],
            description=row["description"],
            latest_version=revision.version,
            created_at=row["created_at"],
        ),
        revision,
    )


async def add_revision(
    conn: asyncpg.Connection, strategy_id: str, definition: Mapping[str, Any]
) -> StrategyRevision | None:
    """The next revision of an existing definition, or `None` when there is no such one. Append-only: a
    watch already pointing at an older one keeps computing it, which is the whole point of pinning."""
    async with conn.transaction():
        definition_id = await conn.fetchval(
            "SELECT id FROM strategy_definitions WHERE strategy_id = $1", strategy_id
        )
        if definition_id is None:
            return None
        return await _insert_revision(conn, int(definition_id), strategy_id, definition)


async def _insert_revision(
    conn: asyncpg.Connection, definition_id: int, strategy_id: str, definition: Mapping[str, Any]
) -> StrategyRevision:
    """The version is chosen inside the statement, for the reason `add_parameter_set` gives."""
    row = await conn.fetchrow(
        """
        INSERT INTO strategy_revisions (definition_id, version, definition)
        VALUES (
            $1,
            coalesce((SELECT max(version) FROM strategy_revisions WHERE definition_id = $1), 0) + 1,
            $2::jsonb
        )
        RETURNING id, definition_id, version, definition, created_at
        """,
        definition_id,
        json.dumps(dict(definition)),
    )
    assert row is not None
    return _revision(row, strategy_id)


async def rename_definition(
    conn: asyncpg.Connection, strategy_id: str, *, name: str, description: str
) -> StrategyDefinition | None:
    """The two things about a definition that are not the rule, updated in place: a decision whose
    provenance changed because somebody fixed a typo would be provenance nobody could trust."""
    row = await conn.fetchrow(
        """
        UPDATE strategy_definitions SET name = $2, description = $3
        WHERE strategy_id = $1
        RETURNING id, strategy_id, name, description, created_at,
                  coalesce((SELECT max(version) FROM strategy_revisions
                            WHERE definition_id = strategy_definitions.id), 0) AS latest_version
        """,
        strategy_id,
        name,
        description,
    )
    return _definition(row) if row else None


async def list_definitions(conn: asyncpg.Connection) -> list[StrategyDefinition]:
    rows = await conn.fetch(
        f"SELECT {_DEFINITION_COLUMNS} FROM strategy_definitions d ORDER BY d.strategy_id"
    )
    return [_definition(row) for row in rows]


async def read_definition(
    conn: asyncpg.Connection, strategy_id: str
) -> StrategyDefinition | None:
    row = await conn.fetchrow(
        f"SELECT {_DEFINITION_COLUMNS} FROM strategy_definitions d WHERE d.strategy_id = $1",
        strategy_id,
    )
    return _definition(row) if row else None


async def list_revisions(conn: asyncpg.Connection, strategy_id: str) -> list[StrategyRevision]:
    rows = await conn.fetch(
        """
        SELECT r.id, r.definition_id, r.version, r.definition, r.created_at
        FROM strategy_revisions r
        JOIN strategy_definitions d ON d.id = r.definition_id
        WHERE d.strategy_id = $1
        ORDER BY r.version DESC
        """,
        strategy_id,
    )
    return [_revision(row, strategy_id) for row in rows]


async def read_revision(conn: asyncpg.Connection, revision_id: int) -> StrategyRevision | None:
    """One revision by its own id — how a recorded decision finds the rule that made it."""
    row = await conn.fetchrow(
        """
        SELECT r.id, r.definition_id, r.version, r.definition, r.created_at, d.strategy_id
        FROM strategy_revisions r
        JOIN strategy_definitions d ON d.id = r.definition_id
        WHERE r.id = $1
        """,
        revision_id,
    )
    return _revision(row, row["strategy_id"]) if row else None


async def read_revision_at(
    conn: asyncpg.Connection, strategy_id: str, version: int | None
) -> StrategyRevision | None:
    """One numbered revision of a definition, or its newest when `version` is `None`."""
    row = await conn.fetchrow(
        """
        SELECT r.id, r.definition_id, r.version, r.definition, r.created_at
        FROM strategy_revisions r
        JOIN strategy_definitions d ON d.id = r.definition_id
        WHERE d.strategy_id = $1 AND ($2::int IS NULL OR r.version = $2)
        ORDER BY r.version DESC
        LIMIT 1
        """,
        strategy_id,
        version,
    )
    return _revision(row, strategy_id) if row else None



async def add_parameter_set(
    conn: asyncpg.Connection,
    strategy_id: str,
    params: Mapping[str, float],
    *,
    strategy_revision_id: int | None = None,
) -> ParameterSet:
    """The next version for this strategy. The version is chosen inside the statement, so two requests
    arriving together do not both read the same last one; the revision is part of the row, not inferred later."""
    row = await conn.fetchrow(
        f"""
        INSERT INTO parameter_sets (strategy_id, version, params, strategy_revision_id)
        VALUES (
            $1,
            coalesce((SELECT max(version) FROM parameter_sets WHERE strategy_id = $1), 0) + 1,
            $2::jsonb,
            $3
        )
        RETURNING {_PARAMETER_SET_COLUMNS}
        """,
        strategy_id,
        json.dumps(dict(params)),
        strategy_revision_id,
    )
    assert row is not None  # an INSERT ... RETURNING that inserted cannot answer nothing
    return _parameter_set(row)


async def read_parameter_set(conn: asyncpg.Connection, parameter_set_id: int) -> ParameterSet | None:
    row = await conn.fetchrow(
        f"SELECT {_PARAMETER_SET_COLUMNS} FROM parameter_sets WHERE id = $1",
        parameter_set_id,
    )
    return _parameter_set(row) if row else None


async def list_parameter_sets(
    conn: asyncpg.Connection, strategy_id: str | None = None
) -> list[ParameterSet]:
    rows = await conn.fetch(
        f"""
        SELECT {_PARAMETER_SET_COLUMNS}
        FROM parameter_sets
        WHERE ($1::text IS NULL OR strategy_id = $1)
        ORDER BY strategy_id, version DESC
        """,
        strategy_id,
    )
    return [_parameter_set(row) for row in rows]



async def put_watch(
    conn: asyncpg.Connection,
    strategy_id: str,
    symbol: str,
    parameter_set_id: int,
    *,
    strategy_revision_id: int | None = None,
) -> Watch:
    """Start watching a pair with a strategy, or point an existing watch at new parameters. Upsert rather
    than insert-or-refuse, and the revision rides the same upsert — so not asking leaves it where it was."""
    row = await conn.fetchrow(
        f"""
        INSERT INTO watches (strategy_id, symbol, parameter_set_id, active, strategy_revision_id)
        VALUES ($1, $2, $3, true, $4)
        ON CONFLICT (strategy_id, symbol) DO UPDATE
            SET parameter_set_id = excluded.parameter_set_id,
                strategy_revision_id = excluded.strategy_revision_id,
                active = true
        RETURNING {_WATCH_COLUMNS}
        """,
        strategy_id,
        symbol,
        parameter_set_id,
        strategy_revision_id,
    )
    assert row is not None
    return _watch(row)


async def set_watch_active(conn: asyncpg.Connection, watch_id: int, active: bool) -> Watch | None:
    row = await conn.fetchrow(
        f"""
        UPDATE watches SET active = $2 WHERE id = $1
        RETURNING {_WATCH_COLUMNS}
        """,
        watch_id,
        active,
    )
    return _watch(row) if row else None


async def list_watches(conn: asyncpg.Connection, *, active_only: bool = False) -> list[Watch]:
    rows = await conn.fetch(
        f"""
        SELECT {_WATCH_COLUMNS}
        FROM watches
        WHERE (NOT $1::boolean OR active)
        ORDER BY strategy_id, symbol
        """,
        active_only,
    )
    return [_watch(row) for row in rows]



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
    strategy_revision_id: int | None = None,
) -> bool:
    """Write one decision. `False` when this bar already had one.

    The bar is the key, so this is safe to call again for a bar already decided — which the
    loop does on every wake, and every restart does for the bar it comes up on.
    """
    written = await conn.fetchval(
        """
        INSERT INTO decisions (
            strategy_id, symbol, parameter_set_id, as_of, action, reason, reason_kind,
            direction, entry, stop, target, rr, score, features, facts, strategy_revision_id
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14::jsonb, $15::jsonb,
                $16)
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
        strategy_revision_id,
    )
    return written is not None


async def last_decision(
    conn: asyncpg.Connection, strategy_id: str, symbol: str
) -> RecordedDecision | None:
    row = await conn.fetchrow(
        f"SELECT {_DECISION_COLUMNS} FROM {_DECISION_SOURCE} "
        "WHERE d.strategy_id = $1 AND d.symbol = $2 ORDER BY d.as_of DESC LIMIT 1",
        strategy_id,
        symbol,
    )
    return _decision(row) if row else None


async def read_decision(conn: asyncpg.Connection, decision_id: int) -> RecordedDecision | None:
    row = await conn.fetchrow(
        f"SELECT {_DECISION_COLUMNS} FROM {_DECISION_SOURCE} WHERE d.id = $1", decision_id
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
        SELECT {_DECISION_COLUMNS} FROM {_DECISION_SOURCE}
        WHERE ($1::text IS NULL OR d.strategy_id = $1)
          AND ($2::text IS NULL OR d.symbol = $2)
          AND ($3::text IS NULL OR d.action = $3)
        ORDER BY d.as_of DESC, d.id DESC
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
    """How many bars this strategy last answered `trade` on — the number a trigger reads. Counted from the
    recorded decisions, so a trigger's threshold and the woken team read the very same fact."""
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



@dataclass(frozen=True)
class BacktestRun:
    id: int
    strategy_id: str
    strategy_revision_id: int | None
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
    strategy_revision_id: int | None = None,
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
            strategy_id, strategy_revision_id, symbol, resolution, range_from, range_to,
            params, costs, report
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9::jsonb)
        RETURNING {_RUN_COLUMNS}
        """,
        strategy_id,
        strategy_revision_id,
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


_PARAMETER_SET_COLUMNS = (
    "id, strategy_id, version, params, created_at, strategy_revision_id"
)

_WATCH_COLUMNS = (
    "id, strategy_id, symbol, parameter_set_id, active, created_at, strategy_revision_id"
)

_RUN_COLUMNS = (
    "id, strategy_id, strategy_revision_id, symbol, resolution, range_from, range_to, "
    "params, costs, report, ran_at"
)


def _run(row: asyncpg.Record) -> BacktestRun:
    return BacktestRun(
        id=row["id"],
        strategy_id=row["strategy_id"],
        strategy_revision_id=row["strategy_revision_id"],
        symbol=row["symbol"],
        resolution=row["resolution"],
        range_from=row["range_from"],
        range_to=row["range_to"],
        params=_json(row["params"]),
        costs=_json(row["costs"]),
        report=_json(row["report"]),
        ran_at=row["ran_at"],
    )



# Joined rather than looked up afterwards: every reader of a decision wants the revision's
# number, and none of them wants to resolve a surrogate id to get it.
_DECISION_SOURCE = "decisions d LEFT JOIN strategy_revisions sr ON sr.id = d.strategy_revision_id"

_DECISION_COLUMNS = (
    "d.id, d.strategy_id, d.symbol, d.parameter_set_id, d.as_of, d.action, d.reason, "
    "d.reason_kind, d.direction, d.entry, d.stop, d.target, d.rr, d.score, d.features, "
    "d.facts, d.created_at, d.strategy_revision_id, sr.version AS strategy_revision"
)


def _json(value: Any) -> Any:
    """asyncpg hands JSONB back as text unless a codec is registered; both are accepted so
    a caller that registered one is not broken by a helper that assumed otherwise."""
    return json.loads(value) if isinstance(value, str | bytes) else value


_DEFINITION_COLUMNS = (
    "d.id, d.strategy_id, d.name, d.description, d.created_at, "
    "coalesce((SELECT max(version) FROM strategy_revisions r WHERE r.definition_id = d.id), 0) "
    "AS latest_version"
)


def _definition(row: asyncpg.Record) -> StrategyDefinition:
    return StrategyDefinition(
        id=row["id"],
        strategy_id=row["strategy_id"],
        name=row["name"],
        description=row["description"],
        latest_version=int(row["latest_version"]),
        created_at=row["created_at"],
    )


def _revision(row: asyncpg.Record, strategy_id: str) -> StrategyRevision:
    return StrategyRevision(
        id=row["id"],
        definition_id=row["definition_id"],
        strategy_id=strategy_id,
        version=row["version"],
        definition=_json(row["definition"]),
        created_at=row["created_at"],
    )


def _parameter_set(row: asyncpg.Record) -> ParameterSet:
    return ParameterSet(
        id=row["id"],
        strategy_id=row["strategy_id"],
        version=row["version"],
        params=_json(row["params"]),
        created_at=row["created_at"],
        strategy_revision_id=row["strategy_revision_id"],
    )


def _watch(row: asyncpg.Record) -> Watch:
    return Watch(
        id=row["id"],
        strategy_id=row["strategy_id"],
        symbol=row["symbol"],
        parameter_set_id=row["parameter_set_id"],
        active=row["active"],
        created_at=row["created_at"],
        strategy_revision_id=row["strategy_revision_id"],
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
        strategy_revision_id=row["strategy_revision_id"],
        strategy_revision=row["strategy_revision"],
    )


def facts_snapshot(facts: Any, gaps: Sequence[Any] = ()) -> dict[str, Any]:
    """The facts an evaluation stood on, as JSON that can be read back. Kept in full rather than as a
    pointer at the archive: replay has to survive the archive's retention and any later correction."""
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
    """The inverse of `facts_snapshot`, and the reason it is written in full: a recorded decision is
    evidence only if it can be re-decided, without asking the archive anything."""
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
