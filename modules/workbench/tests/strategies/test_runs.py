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
from strategies.document import servable, validate
from strategies.queue import RunQueue
from strategies.runs import RunIn

from .builders import catalogue
from .fake_archive import archive_of
from .market import flat, minutes, strategy

COSTS = {"spread": 1.5, "slippage": 0.0, "overnight_long": 0.0, "overnight_short": 0.0, "rollover_hour": 22}
DECLARED = {"fast": {"default": 20, "min": 10, "max": 30, "step": 5}}


def request(**changes) -> RunIn:
    body = {
        "strategy_id": 1, "from": "2026-03-02T00:00:00Z", "to": "2026-03-09T00:00:00Z", "costs": COSTS,
    } | changes
    return RunIn.model_validate(body)


def test_a_parameter_outside_its_declared_range_and_an_unknown_one_are_refused() -> None:
    problems = runs.check_request(request(params={"fast": 40, "slow": 3}), DECLARED, 1_500_000)

    assert {p.path for p in problems} == {"params.fast", "params.slow"}


def test_a_range_past_the_ceiling_is_refused_with_both_numbers() -> None:
    [problem] = runs.check_request(request(to="2030-03-02T00:00:00Z"), DECLARED, 1_500_000)

    assert "1500000" in problem.message and str((4 * 365 + 1) * 1440) in problem.message


def test_a_run_without_costs_is_not_a_request() -> None:
    with pytest.raises(ValueError):
        RunIn.model_validate({"strategy_id": 1, "from": "2026-03-02T00:00:00Z", "to": "2026-03-03T00:00:00Z"})


def test_unnamed_parameters_take_their_defaults() -> None:
    assert runs.resolved_params(request(), DECLARED) == {"fast": 20}


# --- the queue, against a real database and a real worker process --------------------------------------------------

async def _strategy(pool) -> int:
    checked, problems = validate(strategy(), catalogue(), servable({("US100", "MINUTE")}))
    assert checked is not None, problems
    return (await store.create(pool, checked, "operator")).strategy_id


async def _enqueue(pool, strategy_id: int) -> int:
    async with pool.acquire() as conn:
        return await runs.enqueue(conn, request(strategy_id=strategy_id), 1, {})


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
    assert row.engine_version == 1 and row.provenance is not None
    assert row.provenance["series"]["US100@MINUTE"]["bars"] > 0 and row.provenance["seed"] == 1
    async with pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM run_trades WHERE run_id = $1", run_id) == row.report["trades"]


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
async def test_a_running_run_can_be_cancelled_and_the_process_meanwhile_answers(pool) -> None:
    from strategies.app import create_app

    from .slow_worker import main as slow

    run_id = await _enqueue(pool, await _strategy(pool))
    queue = RunQueue(pool, archive_of(MINUTES), _settings(), target=slow)
    await queue.start()
    app = create_app()
    app.state.settings = _settings()
    try:
        await _until(pool, run_id, {"running"})
        await asyncio.sleep(1.5)  # past the spawn: the worker is computing now
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
            started = time.monotonic()
            pong = await client.get("/ping")
            answered_in = time.monotonic() - started
        async with pool.acquire() as conn:
            await runs.cancel(conn, run_id)
        row = await _until(pool, run_id, {"cancelled"}, seconds=10)
    finally:
        await queue.stop()

    assert pong.status_code == 200 and answered_in < 0.5
    assert row.reason == "cancelled by the operator" and queue.busy == 0



@pytest.mark.db
async def test_post_runs_queues_at_once_and_a_missing_strategy_is_a_404(pool) -> None:
    from strategies.app import create_app

    strategy_id = await _strategy(pool)
    app = create_app()
    app.state.settings, app.state.pool = _settings(), pool
    woken = []
    app.state.queue = type("Q", (), {"wake": lambda self: woken.append(1)})()
    body = {"strategy_id": strategy_id, "from": "2026-03-02T00:00:00Z", "to": "2026-03-03T00:00:00Z", "costs": COSTS}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        accepted = await client.post("/runs", json=body)
        missing = await client.post("/runs", json=body | {"strategy_id": 999})

    assert accepted.status_code == 202 and accepted.json()["status"] == "queued" and accepted.json()["revision"] == 1
    assert missing.status_code == 404 and woken == [1]

