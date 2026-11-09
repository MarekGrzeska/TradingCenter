"""`strategy_execute` (`teams-steps`): the decision as a table at the lowest layer, the recipe around it on a fake context,
and one run against the database that the order, its attempt key and the trace land where the spec says."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import pytest

from teams import store
from teams.contract import StepDefinition, TeamDefinition
from teams.models_catalogue import ModelCatalogue
from teams.runner import RunRegistry, execute_run
from teams.steps import StrategyExecuteParams
from teams.steps.strategy_execute import Own, Seen, decide, execute
from teams.tools import ToolDescriptor, ToolOutcome, ToolOutcomeKind, ToolServer, ToolServerRegistry

from .mcp_stand_in import settings_for

BAR = "2026-11-09T14:35:00+00:00"
NOW = datetime(2026, 11, 9, 14, 35, 3, tzinfo=UTC)
WINDOW = "2026-11-02T15:55:00+00:00"


def _params(**overrides: Any) -> StrategyExecuteParams:
    return StrategyExecuteParams.model_validate({"strategy_id": 5, "revision": 1, "symbol": "US100", **overrides})


def _signal(action: str = "enter", *, side: str = "long", engine: str | None = None, age: int = 3, **extra) -> dict:
    position = None if engine is None else {"side": engine, "stop": None, "target": None}
    return {
        "symbol": "US100",
        "action": action,
        "bar_closed_at": BAR,
        "bar_age_seconds": age,
        "order": {"side": side, "kind": "market", "price": None} if action == "enter" else None,
        "position": position,
        "window_from": WINDOW,
        "sizing": {"mode": "margin_fraction", "value": 0.2},
        "exits": [],
        **extra,
    }


def _own(side: str = "long", *, placed_at: datetime = NOW) -> Own:
    return Own(position_id="deal-1", side=side, placed_at=placed_at)


@pytest.mark.parametrize(
    ("seen", "kind", "decision"),
    [
        pytest.param(Seen(_signal(), _params(), 0, 0, None), "enter", "entered", id="fresh enter, flat account"),
        pytest.param(
            Seen(_signal(age=400), _params(max_bar_age_seconds=300), 0, 0, None),
            "none", "skipped", id="bar older than allowed",
        ),
        pytest.param(Seen(_signal(age=4000), _params(), 0, 0, None), "enter", "entered", id="no age limit set"),
        pytest.param(Seen(_signal(), _params(), 1, 0, None), "none", "skipped", id="a manual position on the symbol"),
        pytest.param(Seen(_signal(), _params(), 0, 1, None), "none", "skipped", id="a working order on the symbol"),
        pytest.param(Seen(_signal("hold"), _params(), 0, 0, None), "none", "no_action", id="engine holds"),
        pytest.param(
            Seen(_signal("hold", engine="long"), _params(), 1, 0, _own()), "none", "no_action", id="own matches engine"
        ),
        pytest.param(Seen(_signal("exit", engine="long"), _params(), 1, 0, _own()), "close", "exited", id="exit"),
        pytest.param(Seen(_signal("none"), _params(), 1, 0, _own()), "close", "exited", id="engine flat"),
        pytest.param(
            Seen(_signal("hold", engine="short"), _params(), 1, 0, _own("long")), "close", "exited", id="engine opposite"
        ),
        pytest.param(
            Seen(_signal("none"), _params(), 1, 0, _own(placed_at=NOW - timedelta(days=30))),
            "none", "unknown", id="own position older than the engine's window",
        ),
        pytest.param(
            Seen(_signal(exits=["stop"]), _params(), 0, 0, None), "none", "unsupported", id="strategy with a stop"
        ),
        pytest.param(
            Seen(_signal("exit", engine="long", exits=["stop"]), _params(), 1, 0, _own()),
            "close", "exited", id="an own position still follows a strategy with a stop out",
        ),
        pytest.param(
            Seen(_signal(symbol="GOLD"), _params(), 0, 0, None), "none", "unsupported", id="another symbol's strategy"
        ),
        pytest.param(
            Seen(_signal("enter", side="long"), _params(), 1, 0, _own("long")),
            "none", "skipped", id="second run inside the signal bar, after the entry",
        ),
        pytest.param(
            Seen(_signal("enter", side="short"), _params(), 1, 0, _own("long")),
            "close", "exited", id="engine entering the opposite side",
        ),
        pytest.param(
            Seen(_signal(order={"side": "long", "kind": "limit", "price": 1.0}), _params(), 0, 0, None),
            "none", "unsupported", id="limit order",
        ),
        pytest.param(
            Seen(_signal(), _params(), 2, 0, None, own_unclear="two of ours"), "none", "unknown", id="ownership unclear"
        ),
    ],
)
def test_decide(seen: Seen, kind: str, decision: str) -> None:
    action = decide(seen)
    assert (action.kind, action.decision) == (kind, decision)


# The recipe around `decide`, on a context that answers by tool name.

FILLED = {"outcome": "settled", "status": "FILLED", "id": "deal-9", "reference": "ref-9", "level": 27362.0}


class FakeContext:
    key = "execute"
    team_id = 7
    owner_principal = "operator-1"

    def __init__(self, replies: dict[str, list[ToolOutcome]], placed: list[dict] | None = None) -> None:
        self._replies = replies
        self._placed = placed or []
        self.calls: list[tuple[str, dict, str | None]] = []

    async def call(self, name: str, arguments: dict, *, attempt_key: str | None = None) -> ToolOutcome:
        self.calls.append((name, arguments, attempt_key))
        queue = self._replies[name]
        return queue.pop(0) if len(queue) > 1 else queue[0]

    async def placed_orders(self, symbol: str) -> list[dict]:
        return self._placed


def ok(payload: Any) -> ToolOutcome:
    return ToolOutcome(ToolOutcomeKind.OK, json.dumps(payload), 1)


def _replies(**overrides: list[ToolOutcome]) -> dict[str, list[ToolOutcome]]:
    replies = {
        "strategy_signal": [ok(_signal())],
        "get_positions": [ok({"result": []})],
        "get_working_orders": [ok({"result": []})],
        "get_balance": [ok({"balance": 540.0, "pnl": 0.0, "available": 540.0})],
        "get_last_price": [ok({"close": 27360.0})],
        "size_for_margin": [ok({"size": 0.137})],
        "place_order": [ok(FILLED)],
        "get_candles": [ok({"candles": [{"time": BAR, "open": 27359.0}]})],
        "close_position": [ok(FILLED)],
    }
    replies.update(overrides)
    return replies


def _step(**params: Any) -> StepDefinition:
    return StepDefinition(
        key="execute", recipe="strategy_execute", params={"strategy_id": 5, "revision": 1, "symbol": "US100", **params}
    )


class Clock:
    def __init__(self) -> None:
        self.at = NOW

    def __call__(self) -> datetime:
        return self.at

    async def sleep(self, seconds: float) -> None:
        self.at += timedelta(seconds=seconds)


async def test_an_entry_is_one_market_order_sized_from_the_step_deposit() -> None:
    ctx = FakeContext(_replies())
    clock = Clock()

    result = await execute(_step(deposit_fraction="0.35"), ctx, now=clock, sleep=clock.sleep)

    assert result["decision"] == "entered"
    assert result["sizing"]["source"] == "step"
    assert result["sizing"]["fraction"] == "0.35"
    size_call = next(args for name, args, _ in ctx.calls if name == "size_for_margin")
    assert size_call["margin"] == pytest.approx(540.0 * 0.35)
    _name, order, key = next(call for call in ctx.calls if call[0] == "place_order")
    assert order == {"symbol": "US100", "direction": "BUY", "size": 0.137, "order_type": "MARKET"}
    assert key == f"7:execute:5:1:{BAR}:enter"
    assert result["vs_backtest"] == {"assumed_open": 27359.0, "slippage_points": 3.0}


async def test_without_a_step_deposit_the_document_sizes() -> None:
    result = await execute(_step(), FakeContext(_replies()), now=Clock(), sleep=Clock().sleep)
    assert (result["sizing"]["source"], result["sizing"]["fraction"]) == ("document", "0.2")


async def test_a_bar_the_archive_is_late_with_is_waited_for() -> None:
    late = ToolOutcome(ToolOutcomeKind.REFUSED, "the archive has no MINUTE_5 bar closing at ...", 1)
    ctx = FakeContext(_replies(strategy_signal=[late, late, ok(_signal())]))
    clock = Clock()

    result = await execute(_step(), ctx, now=clock, sleep=clock.sleep)

    assert result["decision"] == "entered"
    assert [name for name, _, _ in ctx.calls].count("strategy_signal") == 3


async def test_a_bar_that_never_comes_ends_skipped_with_the_engine_s_words() -> None:
    late = ToolOutcome(ToolOutcomeKind.REFUSED, "the archive has no MINUTE_5 bar", 1)
    ctx = FakeContext(_replies(strategy_signal=[late]))
    clock = Clock()

    result = await execute(_step(wait_for_bar_seconds=5), ctx, now=clock, sleep=clock.sleep)

    assert result["decision"] == "skipped"
    assert "no MINUTE_5 bar" in result["reason"]
    assert not any(name == "place_order" for name, _, _ in ctx.calls)


async def test_a_strategies_tool_that_does_not_answer_is_unknown_not_a_skip() -> None:
    down = ToolOutcome(ToolOutcomeKind.UNAVAILABLE, "strategies is not configured", 1)
    ctx = FakeContext(_replies(strategy_signal=[down]))

    result = await execute(_step(), ctx, now=Clock(), sleep=Clock().sleep)

    assert result["decision"] == "unknown"
    assert [name for name, _, _ in ctx.calls] == ["strategy_signal"]


async def test_a_refusal_is_asked_again_backing_off_not_every_second() -> None:
    late = ToolOutcome(ToolOutcomeKind.REFUSED, "the archive has no MINUTE_5 bar", 1)
    ctx = FakeContext(_replies(strategy_signal=[late]))
    clock = Clock()

    await execute(_step(wait_for_bar_seconds=30), ctx, now=clock, sleep=clock.sleep)

    assert [name for name, _, _ in ctx.calls].count("strategy_signal") <= 9


async def test_an_entry_taken_but_not_settled_is_unknown() -> None:
    pending = ok({"outcome": "unsettled", "status": "PENDING", "id": None, "reference": "ref-9", "level": None})
    ctx = FakeContext(_replies(place_order=[pending]))

    result = await execute(_step(), ctx, now=Clock(), sleep=Clock().sleep)

    assert result["decision"] == "unknown"
    assert "filled" not in result["summary"]


async def test_an_own_order_that_never_named_its_position_beside_an_unclaimed_one_is_unknown() -> None:
    positions = ok({"result": [{"id": "deal-7", "symbol": "US100", "direction": "BUY", "size": 0.1}]})
    placed = [{"status": "unsettled", "provider_order_id": None, "reference": "ref-7", "created_at": NOW}]
    ctx = FakeContext(_replies(strategy_signal=[ok(_signal("none"))], get_positions=[positions]), placed)

    result = await execute(_step(), ctx, now=Clock(), sleep=Clock().sleep)

    assert result["decision"] == "unknown"
    assert "ref-7" in result["reason"]
    assert not any(call[0] in ("place_order", "close_position") for call in ctx.calls)


async def test_an_order_with_no_known_outcome_is_not_sent_again() -> None:
    lost = ToolOutcome(ToolOutcomeKind.UNAVAILABLE, "timed out", 1)
    ctx = FakeContext(_replies(place_order=[lost]))

    result = await execute(_step(), ctx, now=Clock(), sleep=Clock().sleep)

    assert result["decision"] == "unknown"
    assert [name for name, _, _ in ctx.calls].count("place_order") == 1


async def test_a_gateway_refusal_is_reported_as_it_came_and_not_resized() -> None:
    refused = ToolOutcome(ToolOutcomeKind.REFUSED, "refused: size 0.137 is over the live limit of 0.1", 1)
    ctx = FakeContext(_replies(place_order=[refused]))

    result = await execute(_step(), ctx, now=Clock(), sleep=Clock().sleep)

    assert result["decision"] == "refused"
    assert "over the live limit" in result["reason"]
    assert [name for name, _, _ in ctx.calls].count("place_order") == 1


async def test_the_team_s_own_position_is_closed_when_the_engine_is_flat() -> None:
    positions = ok({"result": [{"id": "deal-1", "symbol": "US100", "direction": "BUY", "size": 0.1}]})
    placed = [
        {"status": "settled", "provider_order_id": "deal-1", "reference": "ref-1", "created_at": NOW - timedelta(hours=4)}
    ]
    ctx = FakeContext(_replies(strategy_signal=[ok(_signal("none"))], get_positions=[positions]), placed)

    result = await execute(_step(), ctx, now=Clock(), sleep=Clock().sleep)

    assert result["decision"] == "exited"
    _name, args, key = next(call for call in ctx.calls if call[0] == "close_position")
    assert args == {"position_id": "deal-1"}
    assert key == f"7:execute:5:1:{BAR}:exit"
    assert not any(call[0] == "place_order" for call in ctx.calls)


# One run against the database: the order, its key and the trace, through the engine.


class RecipeServer(ToolServer):
    """Every tool the recipe calls, answered by name; the account server, so its write tools are writes."""

    WRITES = frozenset({"place_order", "close_position"})

    def __init__(self) -> None:
        super().__init__(settings_for(None), can_move_the_account=True)
        self.replies = _replies()

    @property
    def configured(self) -> bool:
        return True

    async def list_tools(self) -> list[ToolDescriptor]:
        return [
            ToolDescriptor(name=name, description=name, input_schema={}, read_only=name not in self.WRITES)
            for name in self.replies
        ]

    async def call(self, name: str, arguments: dict) -> ToolOutcome:
        return self.replies[name][0]


@pytest.mark.db
async def test_a_step_run_writes_its_order_with_its_key_and_no_usage(pool: asyncpg.Pool) -> None:
    definition = TeamDefinition(steps=[_step(wait_for_bar_seconds=0)])
    settings = settings_for(None)
    async with pool.acquire() as conn:
        team, revision = await store.create_team(
            conn, owner_principal="operator-1", name="a team", description="", definition=definition
        )

    async def one_run() -> int:
        async with pool.acquire() as conn:
            run, _ = await store.create_run(
                conn, team_revision_id=revision["id"], owner_principal="operator-1", agent_keys=["execute"]
            )
        await execute_run(
            pool,
            run_id=run["id"],
            team_id=team["id"],
            owner_principal="operator-1",
            definition=definition,
            provider=None,  # type: ignore[arg-type]
            tool_registry=ToolServerRegistry({"trading-mcp": RecipeServer()}),
            catalogue=ModelCatalogue.from_settings(settings),
            settings=settings,
            registry=RunRegistry(),
        )
        return run["id"]

    first, second = await one_run(), await one_run()

    async with pool.acquire() as conn:
        trades = await store.get_run_trades(conn, run_id=first)
        repeat = await store.get_run_trades(conn, run_id=second)
        usage = await conn.fetchval("SELECT count(*) FROM usage WHERE run_id = ANY($1::bigint[])", [first, second])
        outputs = [
            json.loads(row["output"])
            for row in await conn.fetch(
                "SELECT output FROM run_steps WHERE run_id = ANY($1::bigint[]) ORDER BY run_id", [first, second]
            )
        ]
        statuses = await conn.fetch("SELECT status FROM runs WHERE id = ANY($1::bigint[])", [first, second])

    assert [row["status"] for row in trades] == ["settled"]
    assert trades[0]["agent_key"] == "execute"
    assert repeat == []
    assert usage == 0
    assert [output["decision"] for output in outputs] == ["entered", "skipped"]
    assert {row["status"] for row in statuses} == {"completed"}
