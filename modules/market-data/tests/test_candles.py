"""Reading the archive: a range, the parts of it nobody collected, and coverage.

`market-data-api` 8.1, 8.2 and 8.5. What these hold is that a read answers with what is
there *and* says what is not — an empty stretch inside the window is a fact about
collection, never silence.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fakes import (
    NOW,
    WINDOW,
    at,
    candle,
)

from market_data.coverage import record_coverage
from market_data.models import Candle, CandleSource, Resolution
from market_data.rollups import refresh_all
from market_data.store import write_candles

pytestmark = pytest.mark.db


# --- 8.1: reading a range ------------------------------------------------------------


async def test_a_range_read_answers_with_candles(api, pool) -> None:
    async with pool.acquire() as conn:
        await write_candles(conn, [candle(m) for m in range(3)])

    body = (await api.get("/candles/US100", params={"resolution": "MINUTE", **WINDOW})).json()

    assert [at(c["time"]) for c in body["candles"]] == [
        NOW - timedelta(minutes=m) for m in (2, 1, 0)
    ]


async def test_the_answer_names_the_side_of_the_spread(api, pool) -> None:
    # Never inferred by a consumer. The archive holds bid, and a series quietly compared
    # against an ask-side one is off by a spread that looks like a real move.
    body = (await api.get("/candles/US100")).json()

    assert body["price_side"] == "bid"
    assert body["resolution"] == "MINUTE"


async def test_a_range_read_honours_its_bounds(api, pool) -> None:
    async with pool.acquire() as conn:
        await write_candles(conn, [candle(m) for m in range(5)])

    body = (
        await api.get(
            "/candles/US100",
            params={
                "from": (NOW - timedelta(minutes=3)).isoformat(),
                "to": (NOW - timedelta(minutes=1)).isoformat(),
            },
        )
    ).json()

    assert len(body["candles"]) == 2  # `to` is exclusive, so the minute at NOW-1 is out


async def test_a_derived_resolution_is_served_from_the_derivation(api, pool) -> None:
    async with pool.acquire() as conn:
        await write_candles(conn, [candle(m) for m in range(10)])
        await refresh_all(conn, "US100", NOW - timedelta(minutes=10), NOW)

    body = (await api.get("/candles/US100", params={"resolution": "MINUTE_5", **WINDOW})).json()

    assert body["derived"] is True
    assert body["candles"]


async def test_a_collected_resolution_says_it_was_not_derived(api, pool) -> None:
    body = (await api.get("/candles/US100", params={"resolution": "MINUTE"})).json()
    assert body["derived"] is False


async def test_a_pair_collected_at_a_derivable_resolution_is_served_its_own_candles(
    api, pool
) -> None:
    """The bug this catches was found by reading a live archive: US100 was tracked at
    HOUR, held five thousand hourly candles, and the contract answered with none.

    A resolution being derivable is not the same as this pair having been derived.
    Tracking a pair at HOUR makes ingest fetch and store the provider's own hourly
    candles, and nothing builds a rollup for it, because rollups are refreshed off a
    minute series that pair does not have. Reading the rollup table unconditionally
    therefore answered an empty series while coverage said the range was verified —
    which a consumer reads as "the market was shut", not as "ask somebody".
    """
    hourly = [
        Candle(
            symbol="GOLD",
            resolution=Resolution.HOUR,
            period_start=NOW.replace(minute=0, second=0, microsecond=0) - timedelta(hours=h),
            open=1.0,
            high=2.0,
            low=0.5,
            close=1.5,
            volume=10.0,
            source=CandleSource.HISTORY,
        )
        for h in range(3)
    ]
    async with pool.acquire() as conn:
        await write_candles(conn, hourly)

    body = (
        await api.get(
            "/candles/GOLD",
            params={
                "resolution": "HOUR",
                "from": (NOW - timedelta(hours=6)).isoformat(),
                "to": (NOW + timedelta(hours=1)).isoformat(),
            },
        )
    ).json()

    assert len(body["candles"]) == 3
    assert body["derived"] is False  # they were collected, not computed


async def test_a_range_that_ends_before_it_starts_is_refused_by_name(api) -> None:
    response = await api.get(
        "/candles/US100",
        params={"from": NOW.isoformat(), "to": (NOW - timedelta(hours=1)).isoformat()},
    )

    # A refusal, not a failure: the request is what is wrong, and a 500 would send a
    # caller looking for a fault in the archive.
    assert response.status_code == 422
    assert "is before" in response.json()["detail"]


# --- 8.2: saying which part was never collected --------------------------------------


async def test_a_range_read_marks_what_was_never_collected(api, pool) -> None:
    async with pool.acquire() as conn:
        await record_coverage(
            conn, "US100", Resolution.MINUTE, NOW - timedelta(minutes=10), NOW - timedelta(minutes=5)
        )

    body = (
        await api.get(
            "/candles/US100",
            params={"from": (NOW - timedelta(minutes=10)).isoformat(), "to": NOW.isoformat()},
        )
    ).json()

    [gap] = body["uncovered"]
    assert (at(gap["from"]), at(gap["to"])) == (NOW - timedelta(minutes=5), NOW)


async def test_a_fully_covered_range_marks_nothing(api, pool) -> None:
    # Which is not the same as the range being full of candles: a shut market is covered
    # and empty, and that is a complete answer.
    async with pool.acquire() as conn:
        await record_coverage(
            conn, "US100", Resolution.MINUTE, NOW - timedelta(hours=1), NOW + timedelta(hours=1)
        )

    body = (
        await api.get(
            "/candles/US100",
            params={"from": (NOW - timedelta(minutes=10)).isoformat(), "to": NOW.isoformat()},
        )
    ).json()

    assert body["uncovered"] == []


async def test_a_pair_never_collected_is_uncovered_end_to_end(api) -> None:
    body = (
        await api.get(
            "/candles/US100",
            params={"from": (NOW - timedelta(minutes=10)).isoformat(), "to": NOW.isoformat()},
        )
    ).json()

    assert body["candles"] == []
    assert len(body["uncovered"]) == 1


# --- 8.5: coverage ---------------------------------------------------------------------


async def test_coverage_reads_back_over_the_contract(api, pool) -> None:
    async with pool.acquire() as conn:
        await record_coverage(
            conn,
            "US100",
            Resolution.MINUTE,
            NOW - timedelta(hours=1),
            NOW,
            history_ended=True,
            history_ends_at=NOW - timedelta(minutes=45),
        )

    body = (await api.get("/coverage/US100")).json()

    [covered] = body["ranges"]
    assert (at(covered["from"]), at(covered["to"])) == (NOW - timedelta(hours=1), NOW)
    assert covered["history_ended"] is True
    # Where the read ran out, not the edge it asked about.
    assert at(body["earliest_reachable"]) == NOW - timedelta(minutes=45)


async def test_a_pair_with_no_coverage_says_so_without_failing(api) -> None:
    body = (await api.get("/coverage/GOLD")).json()

    assert body["ranges"] == []
    # Null means the end of provider history has not been reached, not that there is none.
    assert body["earliest_reachable"] is None


