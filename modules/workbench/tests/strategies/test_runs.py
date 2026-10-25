"""Runs as the operator asks for them, and the queue that computes them in a process of its own
(`strategies-backtest`, "Uruchomienie jest zadaniem w tle z limitami")."""

from __future__ import annotations

import asyncio
import json
import time

import httpx
import pytest

from strategies import runs, store
from strategies.config import Settings
from strategies.costs import CostModel
from strategies.document import servable, validate
from strategies.engine import ENGINE_VERSION
from strategies.queue import RunQueue
from strategies.reading import bars_without_minutes
from strategies.runs import RunIn

from .builders import catalogue, run_in_state
from .fake_archive import archive_of
from .market import HOUR, MONDAY, flat, hours, minutes, strategy, walk

COSTS = {"spread": 1.5, "slippage": 0.0, "overnight_long": 0.0, "overnight_short": 0.0, "rollover_hour": 22}
DECLARED = {"fast": {"default": 20, "min": 10, "max": 30, "step": 5}}


def request(**changes) -> RunIn:
    body = {
        "strategy_id": 1, "from": "2026-03-02T00:00:00Z", "to": "2026-03-09T00:00:00Z", "costs": COSTS,
    } | changes
    return RunIn.model_validate(body)


def test_a_parameter_outside_its_declared_range_and_an_unknown_one_are_refused() -> None:
    problems = runs.check_request(request(params={"fast": 40, "slow": 3}), DECLARED, "MINUTE", 1_500_000)

    assert {p.path for p in problems} == {"params.fast", "params.slow"}


def test_a_range_past_the_ceiling_is_refused_with_both_numbers() -> None:
    [problem] = runs.check_request(request(to="2030-03-02T00:00:00Z"), DECLARED, "MINUTE", 1_500_000)

    assert "1500000" in problem.message and str((4 * 365 + 1) * 1440) in problem.message


def test_the_ceiling_counts_candles_of_the_series_fills_are_settled_on() -> None:
    ten_years = request(**{"from": "2016-01-01T00:00:00Z", "to": "2026-01-01T00:00:00Z"})

    assert runs.check_request(ten_years, DECLARED, "MINUTE_5", 1_500_000) == []
    assert [p.path for p in runs.check_request(ten_years, DECLARED, "MINUTE", 1_500_000)] == ["to"]


def test_a_decision_bar_with_no_minute_under_it_is_named_with_the_first_minute_there_is() -> None:
    full = minutes(walk(3))
    # Monday's minutes gone, Tuesday's 10:00 minute alone missing as well.
    kept = {t - MONDAY: row for t, row in zip(full.starts.tolist(), _rows(full), strict=True)
            if t >= MONDAY + 86400 and t != MONDAY + 86400 + 10 * HOUR}
    message = bars_without_minutes(hours(full), minutes(kept), MONDAY, int(full.available[-1]))

    assert message is not None
    assert message.startswith("24 of 72 HOUR bars") and "2026-03-02 00:00 UTC to 2026-03-03 00:00 UTC" in message
    assert "first minute in the range is 2026-03-03 00:00 UTC" in message


def test_a_single_missing_minute_is_not_a_gap() -> None:
    full = minutes(walk(1))
    kept = {t - MONDAY: row for t, row in zip(full.starts.tolist(), _rows(full), strict=True) if t != MONDAY + 600}

    assert bars_without_minutes(hours(full), minutes(kept), MONDAY, int(full.available[-1])) is None


def _rows(series):
    c = series.columns
    return list(zip(c["open"].tolist(), c["high"].tolist(), c["low"].tolist(), c["close"].tolist(), strict=True))


def test_costs_and_without_costs_at_once_are_refused() -> None:
    [problem] = runs.check_request(request(without_costs=True), DECLARED, "MINUTE", 1_500_000)

    assert problem.path == "without_costs"


def test_unnamed_parameters_take_their_defaults() -> None:
    assert runs.resolved_params(request(), DECLARED) == {"fast": 20}


# --- the queue, against a real database and a real worker process --------------------------------------------------

async def _strategy(pool) -> int:
    checked, problems = validate(strategy(), catalogue(), servable({("US100", "MINUTE")}))
    assert checked is not None, problems
    return (await store.create(pool, checked, "operator")).strategy_id


async def _enqueue(pool, strategy_id: int) -> int:
    async with pool.acquire() as conn:
        return await runs.enqueue(conn, request(strategy_id=strategy_id), 1, {}, runs.RunCosts(CostModel(**COSTS), "request"))


async def _until(pool, run_id: int, statuses: set[str], seconds: float = 60.0) -> runs.RunRow:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        async with pool.acquire() as conn:
            row = await runs.get_run(conn, run_id)
        if row is not None and row.status in statuses:
            return row
        await asyncio.sleep(0.2)
    raise AssertionError(f"run {run_id} never reached {statuses}")


def _settings(**changes) -> Settings:
    return Settings(database_url="postgresql://localhost/x", _env_file=None, **changes)  # type: ignore[call-arg]


MINUTES = minutes(flat(0, 5 * 86400, 100.0))


@pytest.mark.db
async def test_a_queued_run_is_computed_in_a_worker_and_leaves_its_trades_and_provenance(pool) -> None:
    run_id = await _enqueue(pool, await _strategy(pool))
    queue = RunQueue(pool, archive_of(MINUTES), _settings())
    await queue.start()
    try:
        row = await _until(pool, run_id, {"done", "failed"})
    finally:
        await queue.stop()

    assert row.status == "done", row.reason
    assert row.engine_version == ENGINE_VERSION and row.provenance is not None
    assert row.provenance["series"]["US100@MINUTE"]["bars"] > 0 and row.provenance["seed"] == 1
    assert row.provenance["execution"] == "MINUTE"
    async with pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM run_trades WHERE run_id = $1", run_id) == row.report["trades"]


@pytest.mark.db
async def test_a_strategy_with_a_stop_over_hours_without_minutes_fails_before_computing(pool) -> None:
    run_id = await _enqueue(pool, await _strategy(pool))
    later = minutes(flat(2 * 86400, 5 * 86400, 100.0))
    queue = RunQueue(pool, archive_of(MINUTES, minutes_served=later), _settings())
    await queue.start()
    try:
        row = await _until(pool, run_id, {"done", "failed"})
    finally:
        await queue.stop()

    assert row.status == "failed" and row.reason is not None
    assert "48 of 120 HOUR bars in the range have no minute under them" in row.reason
    assert "first minute in the range is 2026-03-04 00:00 UTC" in row.reason
    async with pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM run_trades WHERE run_id = $1", run_id) == 0


@pytest.mark.db
async def test_a_run_left_running_by_a_previous_process_is_marked_interrupted(pool) -> None:
    strategy_id = await _strategy(pool)
    async with pool.acquire() as conn:
        run_id = await conn.fetchval(
            "INSERT INTO runs (strategy_id, revision, request, status) VALUES ($1, 1, $2::jsonb, 'running') RETURNING id",
            strategy_id, json.dumps({}),
        )
    queue = RunQueue(pool, archive_of(MINUTES), _settings())
    await queue.start()
    await queue.stop()

    async with pool.acquire() as conn:
        row = await runs.get_run(conn, run_id)
    assert row is not None and (row.status, row.reason) == ("failed", "interrupted by a restart")


@pytest.mark.db
async def test_a_run_past_its_time_limit_is_stopped_and_says_why(pool) -> None:
    from .slow_worker import main as slow

    run_id = await _enqueue(pool, await _strategy(pool))
    queue = RunQueue(pool, archive_of(MINUTES), _settings(run_timeout_seconds=3), target=slow)
    await queue.start()
    try:
        row = await _until(pool, run_id, {"failed"}, seconds=30)
    finally:
        await queue.stop()

    assert "time limit" in (row.reason or "")


@pytest.mark.db
async def test_a_running_run_is_stopped_by_the_queue_when_cancelled_and_the_process_answers_meanwhile(pool) -> None:
    from strategies.app import create_app

    from .slow_worker import main as slow

    run_id = await _enqueue(pool, await _strategy(pool))
    queue = RunQueue(pool, archive_of(MINUTES), _settings(), target=slow)
    app = create_app()
    app.state.settings = _settings()
    await queue.start()
    try:
        await _until(pool, run_id, {"running"})
        # Timed from the moment the run is taken — reading, spawning and computing all happen in this window.
        slowest = 0.0
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
            for _ in range(15):
                started = time.monotonic()
                assert (await client.get("/ping")).status_code == 200
                slowest = max(slowest, time.monotonic() - started)
                await asyncio.sleep(0.1)
        async with pool.acquire() as conn:
            await runs.cancel(conn, run_id)
        deadline = time.monotonic() + 5
        while queue.busy and time.monotonic() < deadline:
            await asyncio.sleep(0.1)
        stopped_by_queue = queue.busy == 0
    finally:
        await queue.stop()

    assert slowest < 0.5
    assert stopped_by_queue, "the queue did not stop the cancelled run's worker"


@pytest.mark.db
async def test_a_run_cancelled_and_deleted_while_its_worker_computes_is_still_stopped(pool) -> None:
    from .slow_worker import main as slow

    run_id = await _enqueue(pool, await _strategy(pool))
    queue = RunQueue(pool, archive_of(MINUTES), _settings(), target=slow)
    await queue.start()
    try:
        await _until(pool, run_id, {"running"})
        async with pool.acquire() as conn:
            await runs.cancel(conn, run_id)
            await runs.delete_runs(conn, [run_id])
        deadline = time.monotonic() + 5
        while queue.busy and time.monotonic() < deadline:
            await asyncio.sleep(0.1)
        stopped_by_queue = queue.busy == 0
    finally:
        await queue.stop()

    assert stopped_by_queue, "the queue left the worker of a deleted run computing"


@pytest.mark.db
async def test_post_runs_queues_at_once_and_a_missing_strategy_is_a_404(pool) -> None:
    from strategies.app import create_app

    strategy_id = await _strategy(pool)
    app = create_app()
    app.state.settings, app.state.pool, app.state.archive = _settings(), pool, archive_of(MINUTES)
    woken = []
    app.state.queue = type("Q", (), {"wake": lambda self: woken.append(1)})()
    body = {"strategy_id": strategy_id, "from": "2026-03-02T00:00:00Z", "to": "2026-03-03T00:00:00Z", "costs": COSTS}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        accepted = await client.post("/runs", json=body)
        missing = await client.post("/runs", json=body | {"strategy_id": 999})

    assert accepted.status_code == 202 and accepted.json()["status"] == "queued" and accepted.json()["revision"] == 1
    assert missing.status_code == 404 and woken == [1]



# --- deleting runs (`strategies-backtest`, "Usunięcie uruchomienia nie obniża licznika prób") -----------------------

async def _trials(pool, strategy_id: int) -> int:
    async with pool.acquire() as conn:
        return (await store.get_strategy(conn, strategy_id)).trials


@pytest.mark.db
async def test_deleting_finished_runs_removes_them_and_their_trades_but_not_the_trials(pool) -> None:
    sid = await _strategy(pool)
    async with pool.acquire() as conn:
        done = [await run_in_state(conn, sid, "done", trades=2) for _ in range(3)]
        failed = await run_in_state(conn, sid, "failed")
        before = await _trials(pool, sid)

        deleted = await runs.delete_runs(conn, [done[0], done[1], failed])
        left = await conn.fetchval("SELECT count(*) FROM runs WHERE id = ANY($1::bigint[])", [done[0], done[1], failed])
        trades = await conn.fetchval("SELECT count(*) FROM run_trades WHERE run_id = ANY($1::bigint[])", done[:2])

    assert before == 3 and deleted == [done[0], done[1], failed]
    assert left == 0 and trades == 0
    assert await _trials(pool, sid) == 3  # the failed run was never one; the two finished ones still are


@pytest.mark.db
async def test_a_run_still_queued_or_running_or_missing_stops_the_whole_deletion(pool) -> None:
    sid = await _strategy(pool)
    async with pool.acquire() as conn:
        done = await run_in_state(conn, sid, "done")
        running = await run_in_state(conn, sid, "running")
        with pytest.raises(runs.NotDeletable) as refused:
            await runs.delete_runs(conn, [done, running, 99_999])
        survivors = await conn.fetchval("SELECT count(*) FROM runs WHERE id = ANY($1::bigint[])", [done, running])

    assert refused.value.missing == [99_999] and refused.value.busy == [(running, "running")]
    assert survivors == 2 and await _trials(pool, sid) == 1


@pytest.mark.db
async def test_a_run_that_finishes_while_it_is_being_deleted_is_counted(pool) -> None:
    sid = await _strategy(pool)
    async with pool.acquire() as conn:
        racing = await run_in_state(conn, sid, "running")
    async with pool.acquire() as finishing, pool.acquire() as deleting:
        async with finishing.transaction():
            await finishing.fetchval("SELECT status FROM runs WHERE id = $1 FOR UPDATE", racing)
            waiting = asyncio.ensure_future(runs.delete_runs(deleting, [racing]))
            await asyncio.sleep(0.3)  # the deletion is now parked on the row the worker holds
            await finishing.execute("UPDATE runs SET status = 'done' WHERE id = $1", racing)
        await waiting

    assert await _trials(pool, sid) == 1
