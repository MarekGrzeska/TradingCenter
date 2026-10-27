"""The tools the conversation calls (`strategies-tools`): what is on the surface, what its descriptions tell a model, and
one test per thing a tool decides — the rules underneath are tested at their own layer."""

from __future__ import annotations

import base64
import json

import httpx
import pytest
from mcp.server.fastmcp.exceptions import ToolError

from strategies import runs, store
from strategies.app import create_app
from strategies.compare import NotComparable, compare, count_problem
from strategies.config import Settings
from strategies.costs import CostModel
from strategies.mcp_app import tool_surface_session
from strategies.queue import RunQueue

from .builders import run_in_state
from .fake_archive import archive_of
from .market import flat, minutes, strategy

EXPECTED = {
    "strategy_language", "list_strategies", "read_strategy", "validate_strategy", "draft_strategy", "save_strategy",
    "run_backtest", "read_backtest", "read_backtest_trades", "compare_runs", "delete_backtests", "strategy_signal",
}
# Characters of the serialized `list_tools()` the conversation reads before every turn. Measured 8 827 on 25 October 2026
# when the surface was written; 10 367 with draft_strategy, the ninth tool, the same day. The headroom is for a description
# that has to say one more thing. 12 454 on 26 October 2026 with delete_backtests and read_backtest_trades, the eleventh;
# 13 214 the same day with strategy_signal, the twelfth (CI on Linux measures a few per cent more than Windows).
SURFACE_CEILING_CHARS = 14_500

COSTS = CostModel(spread=1.0, slippage=0.0, overnight_long=0.0, overnight_short=0.0, rollover_hour=22)
MINUTES = minutes(flat(0, 5 * 86400, 100.0))
RANGE = {"start": "2026-03-02T00:00:00Z", "end": "2026-03-06T00:00:00Z"}


def _app(pool=None, queue=None):
    app = create_app()
    app.state.settings = Settings(database_url="postgresql://localhost/x", _env_file=None)  # type: ignore[call-arg]
    app.state.pool = pool
    app.state.archive = archive_of(MINUTES)
    app.state.queue = queue
    return app


async def _call(app, name: str, **arguments):
    _, structured = await app.state.mcp_server.call_tool(name, arguments)
    return structured


async def test_the_surface_is_the_twelve_tools_and_none_sets_costs() -> None:
    tools = await _app().state.mcp_server.list_tools()

    assert {t.name for t in tools} == EXPECTED
    assert not [t.name for t in tools if "cost" in t.name]


async def test_a_team_gets_the_three_that_read_and_nothing_that_writes() -> None:
    tools = await _app().state.team_mcp_server.list_tools()

    assert {t.name for t in tools} == {"list_strategies", "read_strategy", "strategy_signal"}
    assert all(t.annotations is not None and t.annotations.readOnlyHint for t in tools)


@pytest.mark.db
async def test_a_signal_with_no_closed_bar_is_a_refusal_naming_the_gap_and_counts_nothing(pool) -> None:
    app = _app(pool)
    saved = await _call(app, "save_strategy", document=strategy())

    # The archive's minutes end in March 2026; the bar that closed last, now, is not in it.
    with pytest.raises(ToolError, match="the archive has no HOUR bar closing at"):
        await _call(app, "strategy_signal", strategy_id=saved["strategy_id"], revision=1)
    read = await _call(app, "read_strategy", strategy_id=saved["strategy_id"])

    assert read["trials"] == 0 and read["recent_runs"] == []


async def test_the_descriptions_tell_the_model_how_to_write_and_when_to_run() -> None:
    described = {t.name: t.description or "" for t in await _app().state.mcp_server.list_tools()}

    assert "`notes`" in described["save_strategy"] and "summary" in described["save_strategy"]
    assert "trial" in described["run_backtest"] and "do not run variants" in described["run_backtest"]
    assert "20 s" in described["run_backtest"]


async def test_the_surface_stays_under_its_ceiling() -> None:
    tools = await _app().state.mcp_server.list_tools()
    surface = json.dumps([t.model_dump(exclude_none=True) for t in tools], separators=(",", ":"), ensure_ascii=False)

    assert len(surface) <= SURFACE_CEILING_CHARS, len(surface)


def _principal(application: str) -> dict[str, str]:
    blob = base64.b64encode(json.dumps({"claims": [{"typ": "azp", "val": application}]}).encode()).decode()
    return {"X-MS-CLIENT-PRINCIPAL": blob}


@pytest.mark.parametrize(("application", "refused"), [("operator-mcp-client", False), ("terminal", True)])
async def test_the_tools_are_served_over_the_network_to_a_listed_caller_alone(application: str, refused: bool) -> None:
    app = _app()
    app.state.settings = Settings(
        database_url="postgresql://localhost/x",
        require_authenticated_principal=True,
        tool_caller_application_ids="operator-mcp-client",
        rest_caller_application_ids="terminal",
        _env_file=None,  # type: ignore[call-arg]
    )
    async with (
        tool_surface_session(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client,
    ):
        answered = await client.post(
            "/mcp",
            headers={**_principal(application), "Accept": "application/json, text/event-stream"},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )

    assert (answered.status_code == 403) is refused


@pytest.mark.db
async def test_the_agent_saves_a_revision_as_itself_with_its_changes_and_is_refused_on_a_stale_base(pool) -> None:
    app = _app(pool)
    first = await _call(app, "save_strategy", document=strategy())
    stop = strategy(exits={"stop": "entry_price - 1"})
    second = await _call(app, "save_strategy", document=stop, strategy_id=first["strategy_id"], based_on=1)

    with pytest.raises(ToolError, match="revision 2 was saved after revision 1"):
        await _call(app, "save_strategy", document=strategy(name="late"), strategy_id=first["strategy_id"], based_on=1)
    async with pool.acquire() as conn:
        latest = await store.get_revision(conn, first["strategy_id"])

    assert second["revision"] == 2 and latest.author == "agent" and latest.n == 2
    assert [c["path"] for c in second["changes"]] == ["exits.stop"] and second["summary"]["name"] == "test"


@pytest.mark.db
async def test_a_document_with_problems_is_refused_with_every_one_and_saves_nothing(pool) -> None:
    with pytest.raises(ToolError) as refused:
        await _call(_app(pool), "save_strategy", document=strategy(exits={"max_bars": 0}, universe=["US500"]))
    async with pool.acquire() as conn:
        count = await conn.fetchval("SELECT count(*) FROM strategies")

    # FastMCP puts "Error executing tool save_strategy: " in front of the refusal's own words.
    said = json.loads(str(refused.value).split(": ", 1)[1])
    assert len(said["problems"]) >= 2 and count == 0


class _NoWait:
    """A queue that is woken and never computes: what the tool queued is the question, not what the run found."""

    def listen(self, run_id: int) -> None: ...
    def wake(self) -> None: ...
    async def wait_for(self, run_id: int, timeout: float) -> None: ...


@pytest.mark.db
async def test_without_a_cost_profile_the_agent_runs_with_the_brokers_and_says_so(pool) -> None:
    app = _app(pool, _NoWait())
    saved = await _call(app, "save_strategy", document=strategy())

    answered = await _call(app, "run_backtest", strategy_id=saved["strategy_id"], **RANGE)

    assert answered["costs_source"] == "broker" and answered["costs"]["rollover_hour"] == 21


@pytest.mark.db
async def test_a_run_without_costs_is_the_agents_only_on_request_and_is_recorded_as_such(pool) -> None:
    app = _app(pool, _NoWait())
    saved = await _call(app, "save_strategy", document=strategy())
    described = {t.name: t.description or "" for t in await app.state.mcp_server.list_tools()}

    answered = await _call(app, "run_backtest", strategy_id=saved["strategy_id"], without_costs=True, **RANGE)
    async with pool.acquire() as conn:
        row = await runs.get_run(conn, answered["run_id"])
        profiles = await conn.fetchval("SELECT count(*) FROM cost_profiles")

    assert "operator asks for a run without costs" in described["run_backtest"]
    assert answered["costs_source"] == "none" and row is not None and row.request["without_costs"] is True
    assert profiles == 0


@pytest.mark.db
async def test_a_short_run_answers_within_the_wait_counts_as_a_trial_and_a_second_waits_its_turn(pool) -> None:
    from strategies import costs_store

    settings = Settings(database_url="postgresql://localhost/x", _env_file=None)  # type: ignore[call-arg]
    queue = RunQueue(pool, archive_of(MINUTES), settings)
    app = _app(pool, queue)
    saved = await _call(app, "save_strategy", document=strategy())
    async with pool.acquire() as conn:
        await costs_store.put(conn, "US100", COSTS)
        # A run the agent asked for that has not ended: the next request waits for it.
        waiting = await runs.enqueue(
            conn, runs.RunIn.model_validate({"strategy_id": saved["strategy_id"], "from": RANGE["start"],
                                             "to": RANGE["end"], "costs": COSTS}), 1, {},
            runs.RunCosts(COSTS, "request"), "agent",
        )
    with pytest.raises(ToolError, match=f"run {waiting}"):
        await _call(app, "run_backtest", strategy_id=saved["strategy_id"], **RANGE)
    async with pool.acquire() as conn:
        await runs.cancel(conn, waiting)

    await queue.start()
    try:
        answered = await _call(app, "run_backtest", strategy_id=saved["strategy_id"], **RANGE)
    finally:
        await queue.stop()
    async with pool.acquire() as conn:
        row = await runs.get_run(conn, answered["run_id"])
        summary = await store.get_strategy(conn, saved["strategy_id"])

    assert answered["status"] == "done" and answered["headline"] is not None
    assert row is not None and row.requested_by == "agent" and row.request["costs"]["spread"] == 1.0
    assert summary.trials == 1


def _row(run_id: int, **changes) -> runs.RunRow:
    request = {"from": "2026-03-02T00:00:00Z", "to": "2026-03-06T00:00:00Z", "params": {},
               "costs": COSTS.model_dump()} | changes.pop("request", {})
    fields = {
        "id": run_id, "strategy_id": 1, "revision": 1, "status": "done", "reason": None, "engine_version": 2,
        "request": request, "requested_by": "operator", "queued_at": None, "started_at": None, "finished_at": None,
        "report": {"trades": 3, "total_r": 1.5}, "provenance": None,
    } | changes
    return runs.RunRow(**fields)  # type: ignore[arg-type]


def test_runs_with_different_costs_are_not_compared_and_the_difference_is_named() -> None:
    other = _row(2, request={"costs": COSTS.model_dump() | {"spread": 2.0}})

    with pytest.raises(NotComparable, match="run 2 differs from run 1 in costs: spread"):
        compare([_row(1), other])


def test_runs_sized_by_different_deposits_are_not_compared() -> None:
    with pytest.raises(NotComparable, match="sized by a deposit of 0.1, run 1 by 0.05"):
        compare([_row(1, request={"margin_factor": 0.05}), _row(2, request={"margin_factor": 0.1})])


def test_comparable_runs_stand_side_by_side_without_a_verdict() -> None:
    compared = compare([_row(1), _row(2, report={"trades": 5, "total_r": -2.0})])

    assert [c["total_r"] for c in compared] == [1.5, -2.0]
    assert not {"best", "better", "winner", "rank"} & {k for c in compared for k in c}


@pytest.mark.db
async def test_a_draft_reaches_the_editor_without_a_revision_and_a_save_ends_it(pool) -> None:
    from strategies import drafts

    app = _app(pool)
    saved = await _call(app, "save_strategy", document=strategy())
    sid = saved["strategy_id"]
    drafted = await _call(app, "draft_strategy", document=strategy(exits={"stop": "entry_price - 1"}), strategy_id=sid)
    broken = await _call(app, "draft_strategy", document=strategy(exits={}))
    async with pool.acquire() as conn:
        kept = await drafts.get(conn, sid)
        new = await drafts.get(conn, None)
        summary = await store.get_strategy(conn, sid)

    assert drafted["valid"] is True and broken["valid"] is False and broken["problems"]
    assert kept is not None and kept.document["exits"]["stop"] == "entry_price - 1" and new is not None
    assert summary.latest_revision == 1 and summary.trials == 0

    await _call(app, "save_strategy", document=kept.document, strategy_id=sid, based_on=1)
    async with pool.acquire() as conn:
        assert await drafts.get(conn, sid) is None


@pytest.mark.parametrize("run_ids", [[1], [1, 1], [1, 2, 3, 4, 5, 6]])
def test_one_run_a_repeated_run_or_more_than_five_cannot_be_compared(run_ids: list[int]) -> None:
    assert count_problem(run_ids) == "compare 2 to 5 different runs"
    assert count_problem([1, 2]) is None


@pytest.mark.db
async def test_the_agent_deletes_runs_on_request_and_the_trials_stay_and_a_run_in_progress_stops_it(pool) -> None:
    app = _app(pool)
    saved = await _call(app, "save_strategy", document=strategy())
    async with pool.acquire() as conn:
        finished = await run_in_state(conn, saved["strategy_id"], "done")
        running = await run_in_state(conn, saved["strategy_id"], "running")
    described = {t.name: t.description or "" for t in await app.state.mcp_server.list_tools()}

    with pytest.raises(ToolError, match=f"run {running} is running"):
        await _call(app, "delete_backtests", run_ids=[finished, running])
    with pytest.raises(ToolError, match="1 to 20"):
        await _call(app, "delete_backtests", run_ids=list(range(1, 22)))
    answered = await _call(app, "delete_backtests", run_ids=[finished])
    with pytest.raises(ToolError, match="may have been deleted"):
        await _call(app, "read_backtest", run_id=finished)
    async with pool.acquire() as conn:
        summary = await store.get_strategy(conn, saved["strategy_id"])

    assert answered["deleted"] == [finished] and summary.trials == 1
    assert "operator asked" in described["delete_backtests"] and "no undo" in described["delete_backtests"]


@pytest.mark.db
async def test_the_agent_reads_a_runs_trades_a_page_at_a_time_and_read_backtest_carries_none(pool) -> None:
    app = _app(pool)
    saved = await _call(app, "save_strategy", document=strategy())
    async with pool.acquire() as conn:
        run_id = await run_in_state(conn, saved["strategy_id"], "done", trades=154)

    first = await _call(app, "read_backtest_trades", run_id=run_id, limit=100)
    second = await _call(app, "read_backtest_trades", run_id=run_id, offset=100, limit=100)
    report = await _call(app, "read_backtest", run_id=run_id)
    with pytest.raises(ToolError, match="1 to 100"):
        await _call(app, "read_backtest_trades", run_id=run_id, limit=101)
    with pytest.raises(ToolError, match="may have been deleted"):
        await _call(app, "read_backtest_trades", run_id=run_id + 999)

    assert (first["total"], len(first["trades"]), first["trades"][0]["seq"]) == (154, 100, 0)
    assert (second["total"], len(second["trades"]), second["trades"][0]["seq"]) == (154, 54, 100)
    # A trade without a stop has neither a stop nor R; the rest of it is as recorded.
    assert first["trades"][0]["initial_stop"] is None and first["trades"][0]["result_r"] is None
    assert first["trades"][0]["exit_reason"] == "when" and first["trades"][0]["costs"] == {}
    assert "entry_price" not in json.dumps(report)
