"""The four read-only tools this module announces.

`pending_setups` is the one that shapes the rest. A workbench trigger is a threshold on one
numeric field of one tool's answer, so a count of the setups a strategy is standing on is
exactly the shape a trigger can watch — and the deterministic core finding a candidate is
then what wakes a team. That is the intended seam between this module and the agents: the
core decides, the team reads the same decision and argues with it.

The number is counted from the recorded decisions rather than kept as a running total, so
what a trigger compares against a threshold is the very fact the woken team will read. A
trigger reacting to one value while the team it starts reads another is worse than no
trigger at all (`teams-triggers` learned that on the archive's side first).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from .. import store
from ..catalogue import all_entries
from . import ToolContext

# Applied to every tool here — a structural claim an MCP client can act on, not just a
# convention this module follows (`strategy-tools`, "Zestaw narzędzi wyłącznie czyta").
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)

# How far back `pending_setups` looks by default. A setup from last month is history, not
# something to wake a team about; a day covers every resolution this platform decides on.
DEFAULT_WINDOW = timedelta(days=1)

# The most decisions one call will hand a model. A model reading a hundred refusals learns
# less than it would from ten, and pays for all of them.
DECISION_LIMIT = 25


class StrategyRow(BaseModel):
    id: str
    name: str
    description: str
    resolution: str = Field(description="the bars whose closes drive evaluation")


class PendingSetupsOut(BaseModel):
    strategy_id: str
    # The field a trigger watches. Named plainly because a threshold is written against
    # this name and a rename would silently stop a trigger from ever firing.
    pending: int = Field(description="how many setups this strategy is standing on")
    window_hours: int
    newest_at: datetime | None = Field(
        default=None, description="when the newest of them was decided"
    )


class DecisionRow(BaseModel):
    symbol: str
    as_of: datetime = Field(description="the closing time of the bar decided on")
    action: str
    reason: str | None = None
    reason_kind: str | None = Field(
        default=None,
        description="which layer refused: the strategy, a gap in the data, or a platform limit",
    )
    direction: str | None = None
    entry: float | None = None
    stop: float | None = None
    target: float | None = None
    rr: float | None = None
    score: float | None = None
    features: dict[str, float] = Field(default_factory=dict)


def register(mcp: FastMCP, ctx: ToolContext) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def list_strategies() -> list[StrategyRow]:
        """Which strategies this platform carries, and what rhythm each decides on.

        The catalogue is code in the running image, so this is what exists — not what was
        configured. Reach for `pending_setups` to ask whether one of them is standing on
        anything right now.
        """
        return [
            StrategyRow(
                id=spec.id,
                name=spec.name,
                description=spec.description,
                resolution=spec.resolution,
            )
            for spec in all_entries()
        ]

    @mcp.tool(annotations=READ_ONLY)
    async def pending_setups(strategy_id: str, window_hours: int = 24) -> PendingSetupsOut:
        """How many setups a strategy is standing on — the number to watch for a change.

        A setup here is a decision this platform recorded as tradeable, nothing more: no
        order exists and none will, because this module cannot place one. Read
        `recent_decisions` for what the setups actually say.
        """
        window = timedelta(hours=max(window_hours, 1))
        since = datetime.now(tz=UTC) - window
        async with ctx.pool.acquire() as conn:
            pending = await store.count_pending_setups(conn, strategy_id, since=since)
            rows = await store.list_decisions(
                conn, strategy_id=strategy_id, action="trade", limit=1
            )
        return PendingSetupsOut(
            strategy_id=strategy_id,
            pending=pending,
            window_hours=int(window.total_seconds() // 3600),
            newest_at=rows[0].as_of if rows else None,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def recent_decisions(
        strategy_id: str, symbol: str | None = None, only_setups: bool = False
    ) -> list[DecisionRow]:
        """What a strategy decided lately, newest first, with the reason on every row.

        The refusals are included by default and are the ordinary case — "why has nothing
        happened" is answered by reading them. `only_setups` narrows to the tradeable ones
        when that is the question.
        """
        async with ctx.pool.acquire() as conn:
            rows = await store.list_decisions(
                conn,
                strategy_id=strategy_id,
                symbol=symbol,
                action="trade" if only_setups else None,
                limit=DECISION_LIMIT,
            )
        return [_row(row) for row in rows]

    @mcp.tool(annotations=READ_ONLY)
    async def last_decision(strategy_id: str, symbol: str) -> DecisionRow | None:
        """The most recent decision for one pair, or nothing if this pair was never decided.

        Nothing is an ordinary answer: a watch that has just been created has not reached
        its first closed bar yet.
        """
        async with ctx.pool.acquire() as conn:
            row = await store.last_decision(conn, strategy_id, symbol)
        return _row(row) if row else None


def _row(row) -> DecisionRow:
    return DecisionRow(
        symbol=row.symbol,
        as_of=row.as_of,
        action=row.decision.action,
        reason=row.decision.reason,
        reason_kind=row.reason_kind,
        direction=row.decision.direction,
        entry=row.decision.entry,
        stop=row.decision.stop,
        target=row.decision.target,
        rr=row.decision.rr,
        score=row.decision.score,
        features=dict(row.decision.features),
    )
