"""Collection jobs over the contract — `market-data-jobs`, section 9. The runner's own behaviour and
the store's live next door; what this holds is the shape a consumer sees."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fakes import (
    NOW,
    FakeInstruments,
    FakeInstrumentsBySymbol,
    candle,
)

from market_data.store import write_candles

pytestmark = pytest.mark.db



async def test_adding_several_pairs_is_one_decision_with_one_job(app, api) -> None:
    response = await api.post(
        "/pairs",
        json={
            "pairs": [
                {"symbol": "US100", "resolution": "MINUTE"},
                {"symbol": "US100", "resolution": "HOUR"},
            ],
            "collect_from": (NOW - timedelta(days=5)).isoformat(),
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert len(body["results"]) == 2
    assert all(r["refused"] is None for r in body["results"])
    assert body["job_id"] is not None
    assert app.state.job_runner.notifications == 1


async def test_a_multi_pair_request_refuses_one_without_losing_the_others(app, api) -> None:
    app.state.instruments = FakeInstrumentsBySymbol({"US100": True, "NOPE": False})

    response = await api.post(
        "/pairs",
        json={"pairs": [{"symbol": "US100"}, {"symbol": "NOPE"}]},
    )

    assert response.status_code == 201
    by_symbol = {r["symbol"]: r for r in response.json()["results"]}
    assert by_symbol["US100"]["refused"] is None
    assert by_symbol["US100"]["pair"] is not None
    assert by_symbol["NOPE"]["refused"] is not None
    assert by_symbol["NOPE"]["pair"] is None
    assert [p["symbol"] for p in (await api.get("/pairs")).json()] == ["US100"]


async def test_a_legacy_single_pair_body_still_works(api) -> None:
    # The shape every caller before this change used, still meaning exactly what it did.
    response = await api.post("/pairs", json={"symbol": "US100", "resolution": "MINUTE"})

    assert response.status_code == 201
    body = response.json()
    assert body["results"][0]["symbol"] == "US100"


async def test_pairs_carry_collect_from(api, pool) -> None:
    from_ = NOW - timedelta(days=90)
    await api.post(
        "/pairs", json={"symbol": "US100", "resolution": "MINUTE", "collect_from": from_.isoformat()}
    )

    [pair] = (await api.get("/pairs")).json()
    assert pair["collect_from"] == from_.isoformat().replace("+00:00", "Z")


async def test_estimating_prices_pairs_without_creating_anything(api, pool) -> None:
    response = await api.post(
        "/jobs/estimate",
        json={
            "pairs": [{"symbol": "US100", "resolution": "MINUTE"}],
            "collect_from": (NOW - timedelta(days=5)).isoformat(),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["pairs"][0]["symbol"] == "US100"
    assert body["pairs"][0]["estimated_candles"] > 0
    assert body["total_estimated_candles"] == body["pairs"][0]["estimated_candles"]
    assert (await api.get("/pairs")).json() == []


async def test_estimating_names_a_symbol_the_gateway_does_not_know(app, api) -> None:
    app.state.instruments = FakeInstruments(collectable=False)

    response = await api.post(
        "/jobs/estimate",
        json={"pairs": [{"symbol": "NOPE"}], "collect_from": (NOW - timedelta(days=5)).isoformat()},
    )

    assert response.status_code == 200
    [pair] = response.json()["pairs"]
    assert pair["unknown"] is True
    assert pair["estimated_candles"] == 0


# A start date after now is the one date the module refuses outright, and the refusal has to name
# itself — a 500 would say "the archive broke" about a request that was simply wrong.
async def test_estimating_from_a_future_date_is_refused_with_the_reason(api, pool) -> None:
    # Ahead of the real clock, not of this module's frozen `NOW`: these endpoints compare
    # against `datetime.now(UTC)`, so a date only after `NOW` is simply the recent past.
    future = datetime.now(UTC) + timedelta(days=30)
    response = await api.post(
        "/jobs/estimate",
        json={
            "pairs": [{"symbol": "US100", "resolution": "MINUTE"}],
            "collect_from": future.isoformat(),
        },
    )

    assert response.status_code == 422
    assert "future" in response.json()["detail"]


async def test_tracking_from_a_future_date_is_refused_and_tracks_nothing(api, pool) -> None:
    """The refusal has to cost nothing: `plan_chunks` would raise the same thing, but only
    after the pairs were already tracked and ingest already resynced."""
    future = datetime.now(UTC) + timedelta(days=30)
    response = await api.post(
        "/pairs",
        json={
            "pairs": [{"symbol": "US100", "resolution": "MINUTE"}],
            "collect_from": future.isoformat(),
        },
    )

    assert response.status_code == 422
    assert "future" in response.json()["detail"]
    assert (await api.get("/pairs")).json() == []


async def test_reading_a_job_shows_every_pair_it_touched(api, pool) -> None:
    created = await api.post(
        "/pairs",
        json={
            "pairs": [
                {"symbol": "US100", "resolution": "MINUTE"},
                {"symbol": "US100", "resolution": "HOUR"},
            ],
            "collect_from": (NOW - timedelta(days=2)).isoformat(),
        },
    )
    job_id = created.json()["job_id"]

    response = await api.get(f"/jobs/{job_id}")

    assert response.status_code == 200
    body = response.json()
    pairs = {(c["symbol"], c["resolution"]) for c in body["chunks"]}
    assert pairs == {("US100", "MINUTE"), ("US100", "HOUR")}


async def test_reading_an_unknown_job_is_404(api) -> None:
    response = await api.get("/jobs/999999")
    assert response.status_code == 404


async def test_listing_jobs_narrows_to_one_row_per_pair(api, pool) -> None:
    await api.post(
        "/pairs",
        json={
            "pairs": [
                {"symbol": "US100", "resolution": "MINUTE"},
                {"symbol": "US100", "resolution": "HOUR"},
            ],
            "collect_from": (NOW - timedelta(days=2)).isoformat(),
        },
    )

    response = await api.get("/jobs")

    assert response.status_code == 200
    rows = response.json()
    assert {(r["symbol"], r["resolution"]) for r in rows} == {("US100", "MINUTE"), ("US100", "HOUR")}


async def test_listing_jobs_filtered_to_one_pair(api, pool) -> None:
    await api.post(
        "/pairs",
        json={
            "pairs": [
                {"symbol": "US100", "resolution": "MINUTE"},
                {"symbol": "US100", "resolution": "HOUR"},
            ],
            "collect_from": (NOW - timedelta(days=2)).isoformat(),
        },
    )

    response = await api.get("/jobs", params={"symbol": "US100", "resolution": "MINUTE"})

    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["resolution"] == "MINUTE"


async def test_retrying_wakes_the_runner_and_is_refused_with_nothing_to_retry(app, api, pool) -> None:
    created = await api.post(
        "/pairs",
        json={"symbol": "US100", "resolution": "MINUTE", "collect_from": (NOW - timedelta(days=2)).isoformat()},
    )
    job_id = created.json()["job_id"]
    app.state.job_runner.notifications = 0

    # Nothing has run yet — every chunk is still pending, not failed or interrupted.
    response = await api.post(f"/jobs/{job_id}/retry")

    assert response.status_code == 409
    assert app.state.job_runner.notifications == 0


async def test_retrying_an_unknown_job_is_404(api) -> None:
    response = await api.post("/jobs/999999/retry")
    assert response.status_code == 404


async def _deep_job(api) -> int:
    """One pair, reaching back far enough to plan several chunks. Depth is the point: a `MINUTE` window
    holds about five weeks, so a couple of days is a single chunk, and one chunk cannot be partly anything."""
    created = await api.post(
        "/pairs",
        json={
            "symbol": "US100",
            "resolution": "MINUTE",
            "collect_from": (NOW - timedelta(days=200)).isoformat(),
        },
    )
    return created.json()["job_id"]


async def _set_chunk_states(pool, job_id: int, *states: str) -> None:
    """Put a job's chunks into given states, oldest first. A contract test about how a half-failed job
    reads needs one to exist, and driving the runner to produce one would test the runner instead."""
    async with pool.acquire() as conn:
        ids = [
            row["id"]
            for row in await conn.fetch(
                "SELECT id FROM collection_job_chunks WHERE job_id = $1 ORDER BY id", job_id
            )
        ]
        for chunk_id, state in zip(ids, states, strict=False):
            await conn.execute(
                "UPDATE collection_job_chunks SET state = $2, "
                "candles_written = CASE WHEN $2 = 'done' THEN 500 ELSE 0 END, "
                "failure = CASE WHEN $2 = 'failed' THEN 'the gateway refused with 429' END "
                "WHERE id = $1",
                chunk_id,
                state,
            )


async def test_reading_a_running_job_carries_its_progress_and_the_pair_in_flight(
    api, pool
) -> None:
    job_id = await _deep_job(api)
    await _set_chunk_states(pool, job_id, "done", "running")

    body = (await api.get(f"/jobs/{job_id}")).json()

    assert body["status"] == "running"
    assert body["chunks_done"] == 1
    assert body["chunks_total"] >= 2
    assert body["candles_written"] == 500
    assert body["running_pair"] == {"symbol": "US100", "resolution": "MINUTE"}


async def test_reading_a_partly_failed_job_says_partial_and_names_each_failure(api, pool) -> None:
    job_id = await _deep_job(api)
    # Every chunk settled, one of them badly — which is what `partial` means.
    async with pool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT count(*) FROM collection_job_chunks WHERE job_id = $1", job_id
        )
    await _set_chunk_states(pool, job_id, "failed", *(["done"] * (total - 1)))

    body = (await api.get(f"/jobs/{job_id}")).json()

    assert body["status"] == "partial"
    failed = [chunk for chunk in body["chunks"] if chunk["state"] == "failed"]
    assert failed, "a partial job has to say which chunks failed"
    assert all(chunk["failure"] for chunk in failed), "and name why each one did"


async def test_retrying_a_failed_job_resets_only_it_and_wakes_the_runner(app, api, pool) -> None:
    """The success path through the contract: what comes back is the job as it will now be
    worked, and the runner is told rather than left to find it on its next poll."""
    job_id = await _deep_job(api)
    async with pool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT count(*) FROM collection_job_chunks WHERE job_id = $1", job_id
        )
    await _set_chunk_states(pool, job_id, "failed", *(["done"] * (total - 1)))
    app.state.job_runner.notifications = 0

    response = await api.post(f"/jobs/{job_id}/retry")

    assert response.status_code == 200
    body = response.json()
    assert body["attempt"] == 2
    assert app.state.job_runner.notifications == 1

    # Only the failed chunk went back to pending; a chunk already done is not redone.
    states = [chunk["state"] for chunk in body["chunks"]]
    assert states.count("pending") == 1
    assert states.count("done") == total - 1
    # And the response names the pair and window being retried, so a caller can say what
    # it just asked for.
    [retried] = [chunk for chunk in body["chunks"] if chunk["state"] == "pending"]
    assert retried["symbol"] == "US100"
    assert retried["chunk_start"] and retried["chunk_end"]


async def test_removing_a_settled_job_from_the_history_is_204_and_it_is_gone(
    api, pool
) -> None:
    job_id = await _deep_job(api)
    async with pool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT count(*) FROM collection_job_chunks WHERE job_id = $1", job_id
        )
    await _set_chunk_states(pool, job_id, *(["done"] * total))

    response = await api.delete(f"/jobs/{job_id}")

    assert response.status_code == 204
    assert (await api.get(f"/jobs/{job_id}")).status_code == 404
    assert job_id not in {row["job_id"] for row in (await api.get("/jobs")).json()}


async def test_removing_a_job_with_work_still_open_is_409(api, pool) -> None:
    job_id = await _deep_job(api)
    # Straight from `/pairs`, so every chunk is still pending — the state a runner
    # claims from, and the reason this is refused rather than raced.
    response = await api.delete(f"/jobs/{job_id}")

    assert response.status_code == 409
    assert (await api.get(f"/jobs/{job_id}")).status_code == 200


async def test_removing_an_unknown_job_is_404(api) -> None:
    response = await api.delete("/jobs/999999")
    assert response.status_code == 404


async def test_removing_a_job_keeps_the_candles_it_collected(api, pool) -> None:
    """The 204 says the history entry went; this says the archive did not."""
    job_id = await _deep_job(api)
    async with pool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT count(*) FROM collection_job_chunks WHERE job_id = $1", job_id
        )
        await write_candles(conn, [candle(n) for n in range(3)])
    await _set_chunk_states(pool, job_id, *(["done"] * total))

    await api.delete(f"/jobs/{job_id}")

    async with pool.acquire() as conn:
        left = await conn.fetchval("SELECT count(*) FROM candles WHERE symbol = 'US100'")
    assert left == 3


