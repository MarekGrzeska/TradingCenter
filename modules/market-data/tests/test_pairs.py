"""Managing what is collected, and the refusals that name themselves.

`market-data-api` 8.6 and 8.7, plus the catalogue proxy from `market-data-api`. The
refusals are the half worth reading twice: every one of them says which pair and why, so
a consumer can act on it rather than retry a request that will never be honoured.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fakes import (
    LIMIT,
    NOW,
    FakeIngest,
    FakeInstruments,
    at,
    candle,
)

from market_data.config import Settings
from market_data.coverage import earliest_reachable, record_coverage
from market_data.errors import GatewayRefused, GatewayUnreachable
from market_data.ingest.backfill import FillOutcome
from market_data.models import ESTIMATED_BYTES_PER_CANDLE, Resolution
from market_data.store import read_candles, write_candles
from market_data.tracking import track

pytestmark = pytest.mark.db


# --- 8.6: managing what is collected --------------------------------------------------


async def test_a_pair_can_be_taken_on_over_the_contract(api, pool) -> None:
    response = await api.post("/pairs", json={"symbol": "US100", "resolution": "MINUTE"})

    assert response.status_code == 201
    body = response.json()
    assert len(body["results"]) == 1
    assert body["results"][0]["symbol"] == "US100"
    assert body["results"][0]["pair"]["symbol"] == "US100"
    assert body["results"][0]["refused"] is None
    assert [p["symbol"] for p in (await api.get("/pairs")).json()] == ["US100"]


async def test_asking_deeper_than_the_boundary_drops_it_and_plans_the_whole_range(
    api, pool
) -> None:
    """The recovery path, and the only one an operator has: asking again.

    US100 held a boundary at January 2026 and every request to reach 2024 was silently
    raised to it, planned nothing, and reported itself done. There is no button for this
    and there should not be — reaching deeper *is* the instruction to measure again.
    """
    boundary = NOW - timedelta(days=30)
    async with pool.acquire() as conn:
        await record_coverage(
            conn,
            "US100",
            Resolution.MINUTE,
            boundary,
            NOW,
            history_ended=True,
            history_ends_at=boundary,
        )

    response = await api.post(
        "/pairs",
        json={
            "symbol": "US100",
            "resolution": "MINUTE",
            "collect_from": (NOW - timedelta(days=90)).isoformat(),
        },
    )

    assert response.status_code == 201
    job_id = response.json()["job_id"]
    async with pool.acquire() as conn:
        assert await earliest_reachable(conn, "US100", Resolution.MINUTE) is None
    chunks = (await api.get(f"/jobs/{job_id}")).json()["chunks"]
    assert chunks, "a deeper request must plan the work that measures the boundary again"
    assert at(min(c["chunk_start"] for c in chunks)) == NOW - timedelta(days=90)


async def test_re_adding_a_pair_without_a_date_leaves_the_boundary_alone(api, pool) -> None:
    """A pair's `collect_from` is the deepest moment it was *ever* asked to reach, kept by
    `LEAST` so re-tracking cannot abandon history already promised. Read as this request's
    intent it makes every re-add look like a deeper one — dropping a boundary nobody
    questioned, and replanning the whole span below it."""
    boundary = NOW - timedelta(days=30)
    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT, collect_from=NOW - timedelta(days=90))
        await record_coverage(
            conn,
            "US100",
            Resolution.MINUTE,
            boundary,
            NOW,
            history_ended=True,
            history_ends_at=boundary,
        )

    response = await api.post("/pairs", json={"symbol": "US100", "resolution": "MINUTE"})

    assert response.status_code == 201
    async with pool.acquire() as conn:
        assert await earliest_reachable(conn, "US100", Resolution.MINUTE) == boundary


async def test_pricing_the_same_request_leaves_the_boundary_alone(api, pool) -> None:
    """An estimate is a question. It has to price what the job would do — and it does,
    because planning does not read the boundary either — without ordering anything."""
    boundary = NOW - timedelta(days=30)
    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)
        await record_coverage(
            conn,
            "US100",
            Resolution.MINUTE,
            boundary,
            NOW,
            history_ended=True,
            history_ends_at=boundary,
        )

    response = await api.post(
        "/jobs/estimate",
        json={
            "pairs": [{"symbol": "US100", "resolution": "MINUTE"}],
            "collect_from": (NOW - timedelta(days=90)).isoformat(),
        },
    )

    assert response.status_code == 200
    assert response.json()["pairs"][0]["estimated_candles"] > 0
    async with pool.acquire() as conn:
        assert await earliest_reachable(conn, "US100", Resolution.MINUTE) == boundary


async def test_taking_a_pair_on_starts_collecting_it_without_a_restart(app, api) -> None:
    await api.post("/pairs", json={"symbol": "US100", "resolution": "MINUTE"})

    assert app.state.ingest.syncs == 1


async def test_the_list_carries_how_collection_is_going(api, pool) -> None:
    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)
        await write_candles(conn, [candle(0)])

    [listed] = (await api.get("/pairs")).json()

    assert at(listed["latest_candle"]) == NOW
    assert listed["collection"] in {"collecting", "stalled", "unknown"}


async def test_the_list_carries_how_far_back_the_data_reaches(api, pool) -> None:
    """The panel's "data since", answered without a request per pair.

    It rides on the list because the alternative is the panel asking for coverage once
    per tracked pair just to draw its rows.
    """
    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)
        await write_candles(conn, [candle(0), candle(30)])

    [listed] = (await api.get("/pairs")).json()

    assert at(listed["earliest_candle"]) == NOW - timedelta(minutes=30)


async def test_the_list_carries_how_much_is_collected(api, pool) -> None:
    """How many candles, and roughly how much they take — the date range alone cannot
    say (`market-data-api` spec, "Śledzone pary są zarządzalne przez kontrakt")."""
    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)
        await write_candles(conn, [candle(0), candle(30), candle(60)])

    [listed] = (await api.get("/pairs")).json()

    assert listed["candle_count"] == 3
    assert listed["estimated_bytes"] == 3 * ESTIMATED_BYTES_PER_CANDLE


async def test_a_pair_with_nothing_collected_reports_zero_candles(api, pool) -> None:
    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)

    [listed] = (await api.get("/pairs")).json()

    assert listed["candle_count"] == 0
    assert listed["estimated_bytes"] == 0


async def test_a_late_pair_with_the_market_open_is_reported_stalled(app, api, pool) -> None:
    """The state the panel exists to show, reaching the panel at last.

    `collection_state` could always tell `STALLED` from `MARKET_CLOSED`, and was tested
    doing so — but nothing supplied the one thing it needs, so every late pair came out
    `UNKNOWN` and the distinction never left the unit test.
    """
    app.state.instruments = FakeInstruments(market_open=True)
    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)
        # Hours behind, and the market open: nobody is collecting this.
        await write_candles(conn, [candle(300)])

    [listed] = (await api.get("/pairs")).json()

    assert listed["collection"] == "stalled"


async def test_the_same_lateness_with_the_market_shut_is_not_a_fault(app, api, pool) -> None:
    app.state.instruments = FakeInstruments(market_open=False)
    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)
        await write_candles(conn, [candle(300)])

    [listed] = (await api.get("/pairs")).json()

    assert listed["collection"] == "market_closed"


async def test_a_gateway_that_cannot_say_leaves_the_pair_unknown(app, api, pool) -> None:
    """Not a failure of the read. The list is the archive's own, and not knowing why one
    pair is late is not a reason to refuse all of them."""
    app.state.instruments = FakeInstruments(error=GatewayUnreachable("the gateway is down"))
    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)
        await write_candles(conn, [candle(300)])

    response = await api.get("/pairs")

    assert response.status_code == 200
    assert response.json()[0]["collection"] == "unknown"


async def test_a_fresh_pair_costs_the_gateway_nothing(app, api, pool) -> None:
    """The budget rule. A pair whose newest candle is fresh is `COLLECTING` whatever the
    market is doing, so asking about it would spend the shared allowance to learn nothing
    that changes an answer."""
    instruments = FakeInstruments(market_open=True)
    app.state.instruments = instruments
    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)
        await write_candles(conn, [candle(0, period_start=datetime.now(UTC))])

    [listed] = (await api.get("/pairs")).json()

    assert listed["collection"] == "collecting"
    assert instruments.asked == []


async def test_one_symbol_at_two_resolutions_is_one_question(app, api, pool) -> None:
    """A market is a property of the instrument, not of the resolution it is sampled at."""
    instruments = FakeInstruments(market_open=False)
    app.state.instruments = instruments
    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)
        await track(conn, "US100", Resolution.HOUR, LIMIT)
        await write_candles(conn, [candle(300), candle(300, resolution=Resolution.HOUR)])

    listed = (await api.get("/pairs")).json()

    assert {row["collection"] for row in listed} == {"market_closed"}
    assert instruments.asked == ["US100"]


async def test_a_market_that_was_just_asked_about_is_not_asked_again(app, api, pool) -> None:
    """A shut market is permanently late, so without remembering the answer every read of
    the list spends a request per closed pair. Measured on a live weekend before this
    existed: 74 requests about one instrument that had been shut since Friday."""
    instruments = FakeInstruments(market_open=False)
    app.state.instruments = instruments
    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)
        await write_candles(conn, [candle(300)])

    for _ in range(5):
        assert (await api.get("/pairs")).json()[0]["collection"] == "market_closed"

    assert instruments.asked == ["US100"]


async def test_the_list_says_what_the_last_fill_did(app, api, pool) -> None:
    """Progress leaves the log. The spec asks for what is in flight, what succeeded and
    what failed and why, `zamiast pozostawiać to w logach` — and `Ingest` recorded all of
    it into a report with no caller."""
    outcome = FillOutcome(
        symbol="US100",
        resolution=Resolution.MINUTE,
        requested=31,
        written=29,
        requests=1,
        finished_at=NOW,
    )
    app.state.ingest = FakeIngest(last_fill=outcome)
    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)

    [listed] = (await api.get("/pairs")).json()

    assert listed["last_fill"]["written"] == 29
    assert listed["last_fill"]["requests"] == 1
    assert listed["last_fill"]["failure"] is None
    assert "wrote 29" in listed["last_fill"]["summary"]


async def test_a_failed_fill_reaches_the_list_with_its_reason(app, api, pool) -> None:
    app.state.ingest = FakeIngest(
        last_fill=FillOutcome(
            symbol="NOPE",
            resolution=Resolution.MINUTE,
            requested=100,
            failure="the gateway refused with 404: unknown symbol 'NOPE'",
            finished_at=NOW,
        )
    )
    async with pool.acquire() as conn:
        await track(conn, "NOPE", Resolution.MINUTE, LIMIT)

    [listed] = (await api.get("/pairs")).json()

    assert "unknown symbol" in listed["last_fill"]["failure"]
    assert "fill failed" in listed["last_fill"]["summary"]


async def test_a_pair_whose_fill_has_not_run_says_so_rather_than_inventing_one(
    api, pool
) -> None:
    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)

    [listed] = (await api.get("/pairs")).json()

    assert listed["last_fill"] is None


async def test_a_pair_can_be_deleted_over_the_contract(api, pool) -> None:
    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)
        await write_candles(conn, [candle(0)])

    response = await api.delete("/pairs/US100", params={"resolution": "MINUTE"})

    assert response.status_code == 200
    body = response.json()
    assert body["candles_removed"] == 1
    assert (await api.get("/pairs")).json() == []
    async with pool.acquire() as conn:
        assert await read_candles(conn, "US100", Resolution.MINUTE) == []


async def test_letting_go_of_a_pair_that_was_not_collected_is_a_404(api) -> None:
    response = await api.delete("/pairs/GOLD", params={"resolution": "MINUTE"})

    assert response.status_code == 404
    assert "not being collected" in response.json()["detail"]


async def test_deleting_a_pair_a_404_does_not_touch_anything_else(api, pool) -> None:
    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)
        await write_candles(conn, [candle(0)])

    response = await api.delete("/pairs/GOLD", params={"resolution": "MINUTE"})

    assert response.status_code == 404
    async with pool.acquire() as conn:
        assert len(await read_candles(conn, "US100", Resolution.MINUTE)) == 1


async def test_deleting_a_pair_with_nothing_collected_reports_zero(api, pool) -> None:
    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)

    response = await api.delete("/pairs/US100", params={"resolution": "MINUTE"})

    body = response.json()
    assert body["candles_removed"] == 0
    assert body["removed_from"] is None
    assert body["removed_to"] is None


async def test_reading_deletions_narrowed_to_a_pair(api, pool) -> None:
    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)
        await track(conn, "GOLD", Resolution.HOUR, LIMIT)
    await api.delete("/pairs/US100", params={"resolution": "MINUTE"})
    await api.delete("/pairs/GOLD", params={"resolution": "HOUR"})

    response = await api.get("/deletions", params={"symbol": "US100", "resolution": "MINUTE"})

    assert [d["symbol"] for d in response.json()] == ["US100"]


async def test_reading_deletions_with_none_recorded_is_an_empty_list(api) -> None:
    response = await api.get("/deletions")

    assert response.json() == []


# --- 8.7: refusals that name themselves -----------------------------------------------


async def test_going_over_the_ceiling_is_refused_with_the_reason(app, api, pool) -> None:
    app.state.settings = Settings(
        database_url="postgresql://h:5432/d?sslmode=require",
        database_user="test-user",
        gateway_api_key="test-gateway-key",
        max_tracked_pairs=1,
        _env_file=None,
    )
    await api.post("/pairs", json={"symbol": "US100", "resolution": "MINUTE"})

    response = await api.post("/pairs", json={"symbol": "GOLD", "resolution": "MINUTE"})

    assert response.status_code == 409
    assert "ceiling of 1" in response.json()["detail"]


async def test_a_symbol_the_gateway_will_not_serve_is_refused_with_the_reason(app, api) -> None:
    app.state.instruments = FakeInstruments(collectable=False)

    response = await api.post("/pairs", json={"symbol": "NOPE", "resolution": "MINUTE"})

    assert response.status_code == 422
    assert "archive nothing" in response.json()["detail"]


async def test_a_gateway_that_is_down_is_reported_as_upstream(app, api) -> None:
    app.state.instruments = FakeInstruments(error=GatewayUnreachable("connection refused"))

    response = await api.post("/pairs", json={"symbol": "US100", "resolution": "MINUTE"})

    # 504, not 500: the archive is fine and retrying it as though it were at fault is the
    # wrong response.
    assert response.status_code == 504


async def test_a_failure_never_carries_a_raw_database_error(api, pool) -> None:
    # A database message names tables and columns — more than a caller can use, and more
    # than should travel outward.
    await pool.close()

    response = await api.get("/candles/US100")

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert "see its logs" in detail
    for leak in ("asyncpg", "relation", "SELECT", "password", "candles"):
        assert leak not in detail


# --- specs/market-data-api: the catalogue proxy ----------------------------------------
#
# capital-gateway is not public, so the terminal reaches the catalogue through here
# instead — see design.md, "Terminal osiąga katalog instrumentów przez market-data".


async def test_the_catalogue_is_the_gateways_own_shape_unread(api) -> None:
    response = await api.get("/instruments")

    assert response.status_code == 200
    assert response.json() == {
        "instruments": [],
        "count": 0,
        "truncated": False,
        "max_nodes": None,
        "asset_class": None,
    }


async def test_the_catalogue_forwards_its_query_parameters(api) -> None:
    response = await api.get("/instruments", params={"max_nodes": 50, "asset_class": "CRYPTO"})

    assert response.json()["max_nodes"] == 50
    assert response.json()["asset_class"] == "CRYPTO"


async def test_a_search_reaches_the_gateway_and_comes_back_unmodified(api) -> None:
    response = await api.get("/instruments/search", params={"q": "gold"})

    assert response.status_code == 200
    assert response.json() == [
        {"symbol": "GOLD", "name": "gold", "asset_class": "CRYPTO", "tradeable": True}
    ]


async def test_asset_classes_are_the_gateways_own_list(api) -> None:
    response = await api.get("/asset-classes")

    assert response.status_code == 200
    assert response.json() == ["CRYPTO", "SHARES"]


async def test_a_gateway_refusal_on_the_catalogue_is_not_an_empty_result(app, api) -> None:
    """specs/market-data-api: an odmowa (the gateway's 401 for a missing or wrong caller
    key, or any other refusal) must be distinguishable from an honest empty search — never
    silently turned into one."""
    app.state.instruments = FakeInstruments(error=GatewayRefused(401, "missing or invalid caller key"))

    response = await api.get("/instruments/search", params={"q": "gold"})

    assert response.status_code == 502
    assert response.status_code != 200


async def test_a_gateway_refusal_on_asset_classes_is_reported_not_hidden(app, api) -> None:
    app.state.instruments = FakeInstruments(error=GatewayRefused(401, "missing or invalid caller key"))

    response = await api.get("/asset-classes")

    assert response.status_code == 502


