"""Starting a run on an already-resolved revision — the sequence `POST
/teams/{id}/runs` and the schedule/trigger clock both need once a revision has been
picked, factored out here so a schedule firing at 3am takes exactly the same checks a
click at the terminal does (design.md, "Uruchomienie przebiegu tą samą drogą co
router").

Deliberately not the one to resolve *which* revision runs: a route asks for a team's
current latest, a pinned schedule asks for one from months ago, and a schedule tracking
"latest" asks the same question the route does but at 3am instead of on a click. Mixing
that choice in here would make this the second place it gets made.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import asyncpg

from .. import store
from ..contract import TeamRevisionOut
from ..validation import check_runnable
from .cost import DailyCostLimitReached, limit_from
from .engine import RunRegistry, execute_run
from .trading import DailyOrderLimitReached


async def start_run_on_revision(
    pool: asyncpg.Pool,
    *,
    revision: Mapping[str, Any],
    owner_principal: str,
    catalogue: Any,
    provider: Any,
    tool_registry: Any,
    settings: Any,
    registry: RunRegistry,
) -> tuple[asyncpg.Record, asyncio.Task]:
    """Checks, creates the run and its steps, and starts the background task — the run
    row and that task, so a caller that cares when the run finishes (the clock does; the
    route does not) can await it.

    Raises `validation.DefinitionRefused`, `runner.cost.DailyCostLimitReached` or
    `runner.trading.DailyOrderLimitReached` instead of starting anything — each carries a
    message a caller can show or record as-is.
    """
    definition = TeamRevisionOut.from_row(dict(revision)).definition
    # The saved revision, checked again now — a model dropped from the configuration
    # since it was saved is exactly what this is for (specs/teams-models). The tool half
    # of the same question is asked by the engine, which needs a session to ask it with.
    check_runnable(definition, model_ids=catalogue.ids())

    # The daily ceiling, before anything is created — a run refused halfway is a run
    # that already spent (specs/teams-usage, "Zespół wyczerpał granicę dobową"). Checked
    # against what the team spent since midnight UTC: the module keeps one clock, and a
    # limit that moved with the operator's own timezone would be a different limit in
    # summer — the same reason specs/teams-schedules keeps the clock in UTC too.
    daily_limit = limit_from(definition.limits.daily_limit)
    daily_orders = definition.trading.orders_per_day
    if daily_limit is not None or daily_orders is not None:
        midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        async with pool.acquire() as conn:
            if daily_limit is not None:
                spent = await store.team_cost_since(
                    conn,
                    team_id=revision["team_id"],
                    owner_principal=owner_principal,
                    since=midnight,
                )
                if spent >= daily_limit:
                    raise DailyCostLimitReached(spent, daily_limit)
            if daily_orders is not None:
                # The same midnight as the cost ceiling, and checked in the same place for
                # the same reason a schedule firing at 3am takes the route's own checks: a
                # ceiling the clock does not read is a ceiling that holds only while the
                # operator is watching (specs/teams-trading, "Granica dobowa jest
                # sprawdzana przed utworzeniem przebiegu").
                placed = await store.team_trades_since(
                    conn,
                    team_id=revision["team_id"],
                    owner_principal=owner_principal,
                    since=midnight,
                )
                if placed >= daily_orders:
                    raise DailyOrderLimitReached(placed, daily_orders)

    async with pool.acquire() as conn:
        run, _steps = await store.create_run(
            conn,
            team_revision_id=revision["id"],
            owner_principal=owner_principal,
            agent_keys=[agent.key for agent in definition.agents],
        )

    task = asyncio.create_task(
        execute_run(
            pool,
            run_id=run["id"],
            definition=definition,
            provider=provider,
            tool_registry=tool_registry,
            catalogue=catalogue,
            settings=settings,
            registry=registry,
        )
    )
    registry.register(run["id"], task)
    return run, task
