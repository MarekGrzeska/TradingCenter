"""Orders against a real database: what a run writes as it places them, what the count
stops, and what a revision that never heard of trading limits still does.

The guards themselves are `test_trading_limits.py`; this file is the half that needs
rows — specs/teams-trading, "Każde wywołanie zapisujące zostawia własny wiersz śladu"
and "Granica dobowa jest sprawdzana przed utworzeniem przebiegu".
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest

from teams import store
from teams.contract import AgentDefinition, TeamDefinition, TradingLimits
from teams.models_catalogue import ModelCatalogue
from teams.provider import ProviderChunk, TextDelta, ToolCallRequest, UsageReport
from teams.runner import RunRegistry, execute_run
from teams.tools import ToolOutcomeKind, ToolServer, ToolServerRegistry

from .mcp_stand_in import settings_for
from .scripted_provider import Ask, ScriptedProvider
from .write_server import WriteServer, places_orders

pytestmark = pytest.mark.db

OWNER = "operator-1"


def a_trader(key: str = "trader", *, tools: list[str] | None = None) -> AgentDefinition:
    return AgentDefinition(
        key=key,
        role=key,
        prompt=f"be the {key}",
        model_id="gpt-5.6-luna",
        tools=tools if tools is not None else ["place_order"],
    )


async def _team(pool: asyncpg.Pool, definition: TeamDefinition, *, owner: str = OWNER) -> int:
    async with pool.acquire() as conn:
        team, _revision = await store.create_team(
            conn, owner_principal=owner, name="a team", description="", definition=definition
        )
    return team["id"]


async def _run(
    pool: asyncpg.Pool,
    definition: TeamDefinition,
    provider,
    *,
    server: ToolServer | None = None,
    owner: str = OWNER,
) -> int:
    async with pool.acquire() as conn:
        _team_row, revision = await store.create_team(
            conn, owner_principal=owner, name="a team", description="", definition=definition
        )
        run, _ = await store.create_run(
            conn,
            team_revision_id=revision["id"],
            owner_principal=owner,
            agent_keys=[agent.key for agent in definition.agents],
        )
    settings = settings_for(None)
    await execute_run(
        pool,
        run_id=run["id"],
        definition=definition,
        provider=provider,
        tool_registry=ToolServerRegistry({"trading-mcp": server or WriteServer()}),
        catalogue=ModelCatalogue.from_settings(settings),
        settings=settings,
        registry=RunRegistry(),
    )
    return run["id"]


async def _trades(pool: asyncpg.Pool, run_id: int) -> list[dict]:
    async with pool.acquire() as conn:
        return [dict(row) for row in await store.get_run_trades(conn, run_id=run_id)]


# --- the row, and what it says ---


async def test_a_placed_order_leaves_a_row_naming_the_agent_and_the_order(
    pool: asyncpg.Pool,
) -> None:
    definition = TeamDefinition(agents=[a_trader()])

    run_id = await _run(pool, definition, ScriptedProvider(default=places_orders(1)))
    trades = await _trades(pool, run_id)

    assert len(trades) == 1
    row = trades[0]
    assert row["agent_key"] == "trader"
    assert row["tool_name"] == "place_order"
    assert row["symbol"] == "GOLD"
    assert row["direction"] == "BUY"
    assert row["size"] == 1
    assert row["status"] == "settled"
    assert row["result_status"] == "FILLED"
    assert row["provider_order_id"] == "deal-1"
    assert row["settled_at"] is not None


async def test_a_read_tool_leaves_no_trade_row(pool: asyncpg.Pool) -> None:
    """The set is exactly what a server declared as changing the account — a read call
    is a call, not an order."""
    definition = TeamDefinition(agents=[a_trader(tools=["get_positions"])])

    def reads(ask: Ask) -> Sequence[ProviderChunk]:
        if ask.rounds == 0:
            return [
                ToolCallRequest(id="c1", name="get_positions", arguments={}),
                UsageReport(10, 2, None, None),
            ]
        return [TextDelta("nothing open"), UsageReport(10, 2, None, None)]

    run_id = await _run(pool, definition, ScriptedProvider(default=reads))

    assert await _trades(pool, run_id) == []


async def test_an_unsettled_reply_is_recorded_as_unsettled_with_its_reference(
    pool: asyncpg.Pool,
) -> None:
    pending = json.dumps(
        {"outcome": "unsettled", "status": "PENDING", "id": None, "reference": "ref-9"}
    )
    definition = TeamDefinition(agents=[a_trader()])

    run_id = await _run(
        pool,
        definition,
        ScriptedProvider(default=places_orders(1)),
        server=WriteServer(reply=pending),
    )
    [row] = await _trades(pool, run_id)

    assert row["status"] == "unsettled"
    assert row["reference"] == "ref-9"
    assert row["provider_order_id"] is None


async def test_an_access_failure_leaves_the_row_as_unknown_not_as_failed(
    pool: asyncpg.Pool,
) -> None:
    """specs/teams-trading, "Wywołanie, którego skutek pozostał nieznany": the row exists
    because it was written before the call, and it says the one true thing — this module
    does not know whether the order reached the account."""
    definition = TeamDefinition(agents=[a_trader()])

    run_id = await _run(
        pool,
        definition,
        ScriptedProvider(default=places_orders(1)),
        server=WriteServer(
            reply="the trading-mcp tool server could not be reached", kind=ToolOutcomeKind.UNAVAILABLE
        ),
    )
    [row] = await _trades(pool, run_id)

    assert row["status"] == "unknown"
    assert row["result_status"] is None


async def test_a_refused_order_is_recorded_as_refused(pool: asyncpg.Pool) -> None:
    definition = TeamDefinition(agents=[a_trader()])

    run_id = await _run(
        pool,
        definition,
        ScriptedProvider(default=places_orders(1)),
        server=WriteServer(
            reply="refused: the provider rejected the order — insufficient funds",
            kind=ToolOutcomeKind.REFUSED,
        ),
    )
    [row] = await _trades(pool, run_id)

    assert row["status"] == "refused"


# --- the run count ---


async def test_a_run_reaching_its_order_limit_stops_and_says_orders_not_cost(
    pool: asyncpg.Pool,
) -> None:
    definition = TeamDefinition(
        agents=[a_trader()], trading=TradingLimits(orders_per_run=2)
    )
    server = WriteServer()

    run_id = await _run(pool, definition, ScriptedProvider(default=places_orders(5)), server=server)
    async with pool.acquire() as conn:
        run = dict(await store.get_run(conn, run_id=run_id, owner_principal=OWNER))  # type: ignore[arg-type]

    assert run["status"] == "failed"
    assert "order limit" in run["stopped_reason"]
    assert "cost" not in run["stopped_reason"]
    # Two sent, and the third never reached the server.
    assert server.calls == 2
    trades = await _trades(pool, run_id)
    assert len(trades) == 2
    # The trace of what did happen survives the stop (specs/teams-runs).
    assert all(row["status"] == "settled" for row in trades)


async def test_an_oversized_order_is_refused_without_stopping_the_run(
    pool: asyncpg.Pool,
) -> None:
    """The other half of the same requirement: a size is something an agent can correct,
    so it comes back as a refused call and the run carries on."""
    definition = TeamDefinition(
        agents=[a_trader()], trading=TradingLimits(max_order_size="0.5")
    )
    server = WriteServer()

    run_id = await _run(
        pool,
        definition,
        ScriptedProvider(default=places_orders(1, {"symbol": "GOLD", "size": 5})),
        server=server,
    )
    async with pool.acquire() as conn:
        run = dict(await store.get_run(conn, run_id=run_id, owner_principal=OWNER))  # type: ignore[arg-type]
        calls = [dict(row) for row in await store.get_run_tool_calls(conn, run_id=run_id)]

    assert run["status"] == "completed"
    assert server.calls == 0  # nothing was sent
    assert await _trades(pool, run_id) == []  # and no order was recorded as placed
    # The model was told, in the words it can act on.
    assert calls[0]["outcome"] == "refused"
    assert "smaller" in calls[0]["result_text"]


async def test_a_team_with_no_trading_limits_places_every_order_it_asks_for(
    pool: asyncpg.Pool,
) -> None:
    """specs/teams-trading, "Zespół bez żadnej granicy handlowej" — the operator's own
    call, and this module does not second-guess it."""
    definition = TeamDefinition(agents=[a_trader()])
    server = WriteServer()

    run_id = await _run(pool, definition, ScriptedProvider(default=places_orders(4)), server=server)
    async with pool.acquire() as conn:
        run = dict(await store.get_run(conn, run_id=run_id, owner_principal=OWNER))  # type: ignore[arg-type]

    assert run["status"] == "completed"
    assert server.calls == 4
    assert len(await _trades(pool, run_id)) == 4


async def test_a_revision_saved_before_trading_limits_existed_still_runs(
    pool: asyncpg.Pool,
) -> None:
    """specs/teams-catalogue, "Rewizja z fazy sprzed narzędzi handlowych". The JSONB of an
    older revision carries no `trading` key at all; reading it back must not refuse it and
    must not invent limits for it."""
    async with pool.acquire() as conn:
        team, revision = await store.create_team(
            conn,
            owner_principal=OWNER,
            name="an old team",
            description="",
            definition=TeamDefinition(agents=[a_trader()]),
        )
        # Exactly what a phase-1 row looks like: agents, edges, limits — no `trading`.
        await conn.execute(
            "UPDATE team_revisions SET definition = $2::jsonb WHERE id = $1",
            revision["id"],
            json.dumps(
                {
                    "agents": [
                        {
                            "key": "trader",
                            "role": "trader",
                            "prompt": "be the trader",
                            "guidance": "",
                            "model_id": "gpt-5.6-luna",
                            "tools": ["place_order"],
                        }
                    ],
                    "edges": [],
                    "limits": {"run_limit": None, "daily_limit": None},
                }
            ),
        )
        stored = await store.get_latest_revision(
            conn, team_id=team["id"], owner_principal=OWNER
        )

    from teams.contract import TeamRevisionOut

    definition = TeamRevisionOut.from_row(dict(stored)).definition  # type: ignore[arg-type]
    assert definition.trading.orders_per_run is None
    assert definition.trading.max_order_size is None


# --- the daily count ---


async def test_todays_orders_are_what_the_daily_ceiling_reads(pool: asyncpg.Pool) -> None:
    definition = TeamDefinition(agents=[a_trader()])
    team_id = await _team(pool, definition)

    async with pool.acquire() as conn:
        revision = await store.get_latest_revision(
            conn, team_id=team_id, owner_principal=OWNER
        )
        run, _ = await store.create_run(
            conn,
            team_revision_id=revision["id"],  # type: ignore[index]
            owner_principal=OWNER,
            agent_keys=["trader"],
        )
        step = await store.start_step(conn, run_id=run["id"], agent_key="trader")
        for _ in range(3):
            await store.record_trade(
                conn,
                run_id=run["id"],
                run_step_id=step["id"],
                agent_key="trader",
                tool_name="place_order",
                symbol="GOLD",
                direction="BUY",
                size=None,
                level=None,
            )

        midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        placed = await store.team_trades_since(
            conn, team_id=team_id, owner_principal=OWNER, since=midnight
        )
        yesterday = await store.team_trades_since(
            conn,
            team_id=team_id,
            owner_principal=OWNER,
            since=midnight + timedelta(days=1),
        )
        others = await store.team_trades_since(
            conn, team_id=team_id, owner_principal="somebody-else", since=midnight
        )

    assert placed == 3
    # A window this team placed nothing in, and another operator's view of the same team.
    assert yesterday == 0
    assert others == 0


async def test_an_unsettled_order_still_counts_against_the_day(pool: asyncpg.Pool) -> None:
    """A ceiling that forgave an order whose reply never came back would be one an outage
    could walk through."""
    definition = TeamDefinition(agents=[a_trader()])
    run_id = await _run(
        pool,
        definition,
        ScriptedProvider(default=places_orders(1)),
        server=WriteServer(reply="unreachable", kind=ToolOutcomeKind.UNAVAILABLE),
    )

    async with pool.acquire() as conn:
        run = await store.get_run(conn, run_id=run_id, owner_principal=OWNER)
        revision = await conn.fetchrow(
            "SELECT team_id FROM team_revisions WHERE id = $1", run["team_revision_id"]  # type: ignore[index]
        )
        midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        placed = await store.team_trades_since(
            conn,
            team_id=revision["team_id"],  # type: ignore[index]
            owner_principal=OWNER,
            since=midnight,
        )

    assert placed == 1
