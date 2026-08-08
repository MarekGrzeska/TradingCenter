from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from market_data.app import app, candle_sink
from market_data.config import Settings
from market_data.coverage import record_coverage
from market_data.errors import GatewayUnreachable
from market_data.hub import CandleChange, Hub, Snapshot
from market_data.ingest.backfill import FillOutcome
from market_data.models import Candle, CandleSource, Resolution
from market_data.rollups import refresh_all
from market_data.store import read_candles, write_candles
from market_data.tracking import track

pytestmark = pytest.mark.db

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
LIMIT = 20

# Every read of a range says which range, and this is why.
#
# `/candles` defaults to the last day *of the real clock*, so a test that writes candles
# around a fixed `NOW` and then omits the window is only asserting anything while the wall
# clock happens to be within a day of that constant. Two tests did, and they began failing
# at noon on 2026-08-08 — a day after `NOW`, having passed every run before it, for no
# reason connected to the code.
WINDOW = {
    "from": (NOW - timedelta(hours=1)).isoformat(),
    "to": (NOW + timedelta(minutes=1)).isoformat(),
}


def candle(offset: int = 0, **overrides) -> Candle:
    return Candle(
        **{
            "symbol": "US100",
            "resolution": Resolution.MINUTE,
            "period_start": NOW - timedelta(minutes=offset),
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 10.0,
            "source": CandleSource.HISTORY,
            **overrides,
        }
    )


class FakeInstruments:
    def __init__(
        self,
        collectable: bool = True,
        error: Exception | None = None,
        market_open: bool | None = None,
    ):
        self.collectable = collectable
        self.error = error
        # What the gateway would say about the instrument's session. `None` is the
        # default because it is the honest one for a fake: no answer, so `UNKNOWN`.
        self.market_open = market_open
        self.asked: list[str] = []

    async def is_collectable(self, symbol: str, resolution: Resolution) -> bool:
        if self.error is not None:
            raise self.error
        return self.collectable

    async def is_market_open(self, symbol: str) -> bool | None:
        self.asked.append(symbol)
        if self.error is not None:
            raise self.error
        return self.market_open


class FakeInstrumentsBySymbol:
    """Like `FakeInstruments`, but collectability varies per symbol — for a multi-pair
    request where one symbol is refused and the others are not."""

    def __init__(self, collectable: dict[str, bool]) -> None:
        self._collectable = collectable

    async def is_collectable(self, symbol: str, resolution: Resolution) -> bool:
        return self._collectable.get(symbol, False)

    async def is_market_open(self, symbol: str) -> bool | None:
        return None


class FakeIngest:
    """Stands in for the supervisor: reconciles, and remembers what a fill did."""

    def __init__(self, last_fill=None) -> None:
        self.syncs = 0
        self.running: set = set()
        self.started_at = NOW
        self._last_fill = last_fill

    async def sync(self) -> None:
        self.syncs += 1

    def last_fill(self, symbol: str, resolution: Resolution):
        return self._last_fill


class FakeJobRunner:
    """Stands in for the runner: real chunks still get worked, but by whatever executes
    them directly in a test — `notify()` here is just observed, never acted on."""

    def __init__(self) -> None:
        self.notifications = 0

    def notify(self) -> None:
        self.notifications += 1


@pytest.fixture
async def pool(migrated_url: str):
    from market_data.db import pool as make_pool

    async with make_pool(migrated_url, max_size=5) as created:
        async with created.acquire() as conn:
            await conn.execute("TRUNCATE candles, derived_candles, tracked_pairs, coverage_ranges, collection_jobs, collection_job_chunks")
        yield created


@pytest.fixture(autouse=True)
def _forget_market_status():
    """The market-status cache is module-level, so one test's answer would otherwise be
    the next test's premise."""
    from market_data.app import _market_status_cache

    _market_status_cache.clear()
    yield
    _market_status_cache.clear()


@pytest.fixture
async def api(pool, migrated_url: str):
    """The app wired to a real database, with the two things that reach outward faked.

    The lifespan is bypassed rather than run: it would start ingest, which would try to
    reach a gateway that is not there. What is under test here is the contract.
    """
    app.state.pool = pool
    app.state.hub = Hub()
    app.state.settings = Settings(database_url=migrated_url, _env_file=None)
    app.state.instruments = FakeInstruments()
    app.state.ingest = FakeIngest()
    app.state.job_runner = FakeJobRunner()

    # `raise_app_exceptions=False` so the app's own error handling is what the test sees.
    # With the default, the transport re-raises whatever the app raised and the 500 the
    # handler produced — the thing under test in 8.7 — never reaches the response.
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://archive.test") as client:
        yield client


# --- 8.1: reading a range ------------------------------------------------------------


async def test_a_range_read_answers_with_candles(api, pool) -> None:
    async with pool.acquire() as conn:
        await write_candles(conn, [candle(m) for m in range(3)])

    body = (await api.get("/candles/US100", params={"resolution": "MINUTE", **WINDOW})).json()

    assert [_at(c["time"]) for c in body["candles"]] == [
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
    assert (_at(gap["from"]), _at(gap["to"])) == (NOW - timedelta(minutes=5), NOW)


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
        )

    body = (await api.get("/coverage/US100")).json()

    [covered] = body["ranges"]
    assert (_at(covered["from"]), _at(covered["to"])) == (NOW - timedelta(hours=1), NOW)
    assert covered["history_ended"] is True
    assert _at(body["earliest_reachable"]) == NOW - timedelta(hours=1)


async def test_a_pair_with_no_coverage_says_so_without_failing(api) -> None:
    body = (await api.get("/coverage/GOLD")).json()

    assert body["ranges"] == []
    # Null means the end of provider history has not been reached, not that there is none.
    assert body["earliest_reachable"] is None


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


async def test_taking_a_pair_on_starts_collecting_it_without_a_restart(api) -> None:
    await api.post("/pairs", json={"symbol": "US100", "resolution": "MINUTE"})

    assert app.state.ingest.syncs == 1


async def test_the_list_carries_how_collection_is_going(api, pool) -> None:
    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)
        await write_candles(conn, [candle(0)])

    [listed] = (await api.get("/pairs")).json()

    assert _at(listed["latest_candle"]) == NOW
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

    assert _at(listed["earliest_candle"]) == NOW - timedelta(minutes=30)


async def test_a_late_pair_with_the_market_open_is_reported_stalled(api, pool) -> None:
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


async def test_the_same_lateness_with_the_market_shut_is_not_a_fault(api, pool) -> None:
    app.state.instruments = FakeInstruments(market_open=False)
    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)
        await write_candles(conn, [candle(300)])

    [listed] = (await api.get("/pairs")).json()

    assert listed["collection"] == "market_closed"


async def test_a_gateway_that_cannot_say_leaves_the_pair_unknown(api, pool) -> None:
    """Not a failure of the read. The list is the archive's own, and not knowing why one
    pair is late is not a reason to refuse all of them."""
    app.state.instruments = FakeInstruments(error=GatewayUnreachable("the gateway is down"))
    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)
        await write_candles(conn, [candle(300)])

    response = await api.get("/pairs")

    assert response.status_code == 200
    assert response.json()[0]["collection"] == "unknown"


async def test_a_fresh_pair_costs_the_gateway_nothing(api, pool) -> None:
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


async def test_one_symbol_at_two_resolutions_is_one_question(api, pool) -> None:
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


async def test_a_market_that_was_just_asked_about_is_not_asked_again(api, pool) -> None:
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


async def test_the_list_says_what_the_last_fill_did(api, pool) -> None:
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


async def test_a_failed_fill_reaches_the_list_with_its_reason(api, pool) -> None:
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


async def test_a_pair_can_be_let_go_over_the_contract(api, pool) -> None:
    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)
        await write_candles(conn, [candle(0)])

    response = await api.delete("/pairs/US100", params={"resolution": "MINUTE"})

    assert response.status_code == 204
    assert (await api.get("/pairs")).json() == []
    # The candles stay. An archive that deletes on a configuration change is not one.
    async with pool.acquire() as conn:
        assert len(await read_candles(conn, "US100", Resolution.MINUTE)) == 1


async def test_letting_go_of_a_pair_that_was_not_collected_is_a_404(api) -> None:
    response = await api.delete("/pairs/GOLD", params={"resolution": "MINUTE"})

    assert response.status_code == 404
    assert "not being collected" in response.json()["detail"]


# --- 8.7: refusals that name themselves -----------------------------------------------


async def test_going_over_the_ceiling_is_refused_with_the_reason(api, pool) -> None:
    app.state.settings = Settings(
        database_url="postgresql://u:p@h/d", max_tracked_pairs=1, _env_file=None
    )
    await api.post("/pairs", json={"symbol": "US100", "resolution": "MINUTE"})

    response = await api.post("/pairs", json={"symbol": "GOLD", "resolution": "MINUTE"})

    assert response.status_code == 409
    assert "ceiling of 1" in response.json()["detail"]


async def test_a_symbol_the_gateway_will_not_serve_is_refused_with_the_reason(api) -> None:
    app.state.instruments = FakeInstruments(collectable=False)

    response = await api.post("/pairs", json={"symbol": "NOPE", "resolution": "MINUTE"})

    assert response.status_code == 422
    assert "archive nothing" in response.json()["detail"]


async def test_a_gateway_that_is_down_is_reported_as_upstream(api) -> None:
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


# --- 9: collection jobs, over the contract ----------------------------------------------


async def test_adding_several_pairs_is_one_decision_with_one_job(api) -> None:
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


async def test_a_multi_pair_request_refuses_one_without_losing_the_others(api) -> None:
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


async def test_estimating_names_a_symbol_the_gateway_does_not_know(api) -> None:
    app.state.instruments = FakeInstruments(collectable=False)

    response = await api.post(
        "/jobs/estimate",
        json={"pairs": [{"symbol": "NOPE"}], "collect_from": (NOW - timedelta(days=5)).isoformat()},
    )

    assert response.status_code == 200
    [pair] = response.json()["pairs"]
    assert pair["unknown"] is True
    assert pair["estimated_candles"] == 0


# A start date after now is the one date the module refuses outright, and the refusal has
# to name itself — a 500 would say "the archive broke" about a request that was simply
# wrong (`market-data-jobs` spec, "Data w przyszłości").
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


async def test_retrying_wakes_the_runner_and_is_refused_with_nothing_to_retry(api, pool) -> None:
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
    """One pair, reaching back far enough to plan several chunks.

    Depth is the point: a `MINUTE` window holds `MAX_BARS_PER_FILL` candles — about five
    weeks — so a request for the last couple of days is a single chunk, and a job of one
    chunk cannot be partly anything.
    """
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
    """Put a job's chunks into given states, oldest chunk first.

    A contract test about how a running or half-failed job *reads* needs one to exist,
    and driving the runner to produce one would be testing the runner instead. States
    shorter than the chunk list leave the rest as they were.
    """
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


async def test_retrying_a_failed_job_resets_only_it_and_wakes_the_runner(api, pool) -> None:
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


# --- 8.8: the schema describes the HTTP contract and nothing else ---------------------


async def test_the_websocket_path_is_absent_from_the_schema(api) -> None:
    """OpenAPI has no vocabulary for WebSocket payloads, so a path that appeared there
    would describe a contract it cannot actually state — and the README would become the
    second description rather than the only one."""
    schema = (await api.get("/openapi.json")).json()

    assert "/ws/candles" not in schema["paths"]
    assert not [path for path in schema["paths"] if path.startswith("/ws")]


async def test_the_http_routes_are_all_described(api) -> None:
    paths = (await api.get("/openapi.json")).json()["paths"]

    assert {
        "/candles/{symbol}",
        "/coverage/{symbol}",
        "/pairs",
        "/pairs/{symbol}",
        "/jobs/estimate",
        "/jobs",
        "/jobs/{job_id}",
        "/jobs/{job_id}/retry",
    } <= set(paths)


async def test_the_schema_says_which_side_of_the_spread_is_stored(api) -> None:
    schema = (await api.get("/openapi.json")).json()

    assert "bid" in schema["info"]["description"]


# --- 8.3, 8.4 and 8.10: the snapshot and what follows it -------------------------------


async def test_a_subscriber_is_handed_the_settled_series_first(pool) -> None:
    hub = Hub()
    async with pool.acquire() as conn:
        await write_candles(conn, [candle(m) for m in range(3)])
    received, collect = _collector()

    await hub.subscribe("US100", Resolution.MINUTE, collect, _settled(pool))

    [snapshot] = received
    assert isinstance(snapshot, Snapshot)
    assert [c.period_start for c in snapshot.candles] == [
        NOW - timedelta(minutes=m) for m in (2, 1, 0)
    ]


async def test_the_snapshot_carries_the_period_still_being_built(pool) -> None:
    # A chart joining midway would otherwise be missing the bar the price is actually in.
    hub = Hub()
    forming = candle(0, source=CandleSource.STREAM, forming=True)
    await hub.publish("US100", Resolution.MINUTE, forming)
    received, collect = _collector()

    await hub.subscribe("US100", Resolution.MINUTE, collect, _settled(pool))

    assert received[0].forming is not None
    assert received[0].forming.period_start == forming.period_start


async def test_a_closed_candle_clears_the_forming_one(pool) -> None:
    hub = Hub()
    await hub.publish("US100", Resolution.MINUTE, candle(0, forming=True))
    await hub.publish("US100", Resolution.MINUTE, candle(0, forming=False))
    received, collect = _collector()

    await hub.subscribe("US100", Resolution.MINUTE, collect, _settled(pool))

    assert received[0].forming is None


async def test_changes_after_the_snapshot_say_whether_a_candle_has_closed(pool) -> None:
    """8.4."""
    hub = Hub()
    received, collect = _collector()
    await hub.subscribe("US100", Resolution.MINUTE, collect, _settled(pool))

    await hub.publish("US100", Resolution.MINUTE, candle(0, forming=True))
    await hub.publish("US100", Resolution.MINUTE, candle(0, forming=False))

    changes = [m for m in received if isinstance(m, CandleChange)]
    assert [c.candle.forming for c in changes] == [True, False]


async def test_a_period_never_arrives_both_in_the_snapshot_and_after_it(
    pool, monkeypatch
) -> None:
    """8.10, and the reason the hold exists.

    Ingest stores a candle and then publishes it. If the store can commit outside the
    hold, there is a moment between the two where a subscriber's snapshot query sees the
    candle *and* the change carrying it is still to come — two bars for one period, on
    every chart that happened to connect just then.

    That moment is opened deliberately here rather than hoped for. Racing two tasks and
    trusting the scheduler to hit a window a few microseconds wide is how a test comes to
    pass against an implementation that has no hold at all, which this one did before it
    was written this way.
    """
    import market_data.app as app_module

    hub = Hub()
    committed = asyncio.Event()
    may_finish = asyncio.Event()
    real_store = app_module.store_closed_candle

    async def store_then_wait(pool_, stored_candle) -> None:
        await real_store(pool_, stored_candle)
        committed.set()
        await may_finish.wait()

    monkeypatch.setattr(app_module, "store_closed_candle", store_then_wait)

    sink = candle_sink(pool, hub)
    received, collect = _collector()

    producing = asyncio.create_task(sink(candle(0, source=CandleSource.STREAM)))
    await committed.wait()

    # The candle is now in the database and has not been broadcast. A subscriber attaching
    # at this instant is the whole hazard.
    attaching = asyncio.create_task(
        hub.subscribe("US100", Resolution.MINUTE, collect, _settled(pool))
    )
    await asyncio.sleep(0.05)  # every chance to slip in, if it can
    may_finish.set()
    await producing
    await attaching

    seen = [c.period_start for c in received[0].candles]
    seen += [m.candle.period_start for m in received[1:] if isinstance(m, CandleChange)]

    assert len(seen) == len(set(seen)), "a period arrived twice across the seam"
    assert len(seen) == 1


async def test_no_period_falls_between_the_snapshot_and_the_changes(pool) -> None:
    # The other half of the same guarantee: nothing may be missing either. A hundred
    # candles stored and published while a subscriber attaches somewhere in the middle.
    hub = Hub()
    sink = candle_sink(pool, hub)
    received, collect = _collector()

    async def produce():
        for m in range(100, 0, -1):
            await sink(candle(m, source=CandleSource.STREAM))

    async def attach():
        await asyncio.sleep(0)
        await hub.subscribe("US100", Resolution.MINUTE, collect, _settled(pool))

    await asyncio.gather(produce(), attach())

    seen = {c.period_start for c in received[0].candles}
    seen |= {m.candle.period_start for m in received[1:] if isinstance(m, CandleChange)}
    async with pool.acquire() as conn:
        stored = {c.period_start for c in await read_candles(conn, "US100", Resolution.MINUTE)}

    assert stored <= seen, "a candle was stored that the subscriber never learned about"


async def test_a_subscriber_that_fails_does_not_take_the_others_with_it(pool) -> None:
    # A socket that dies *after* subscribing, which is the case that happens: a failure
    # during the snapshot is the subscriber's own problem and is left to propagate, but
    # one during a broadcast must cost only that subscriber.
    hub = Hub()
    good, collect_good = _collector()
    sent = 0

    async def dies_after_the_snapshot(_message):
        nonlocal sent
        sent += 1
        if sent > 1:
            raise RuntimeError("this socket is gone")

    await hub.subscribe("US100", Resolution.MINUTE, collect_good, _settled(pool))
    await hub.subscribe("US100", Resolution.MINUTE, dies_after_the_snapshot, _settled(pool))
    assert hub.subscriber_count("US100", Resolution.MINUTE) == 2

    await hub.publish("US100", Resolution.MINUTE, candle(0))

    assert any(isinstance(m, CandleChange) for m in good)
    assert hub.subscriber_count("US100", Resolution.MINUTE) == 1


async def test_a_subscriber_stops_receiving_once_it_leaves(pool) -> None:
    hub = Hub()
    received, collect = _collector()
    await hub.subscribe("US100", Resolution.MINUTE, collect, _settled(pool))

    await hub.unsubscribe("US100", Resolution.MINUTE, collect)
    await hub.publish("US100", Resolution.MINUTE, candle(0))

    assert not [m for m in received if isinstance(m, CandleChange)]


# --- 8.9: subscribing to something nobody chose to collect -----------------------------


class FakeWebSocket:
    """Enough of a WebSocket to drive the handler's decisions.

    The handler is exercised directly rather than through a test client, because a client
    runs the app on its own event loop and the database pool belongs to this one.
    """

    def __init__(self, **params):
        self.query_params = params
        self.app = app
        self.accepted = False
        self.closed: tuple[int, str] | None = None
        self.sent: list[dict] = []

    async def accept(self) -> None:
        self.accepted = True

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed = (code, reason)

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)

    async def receive_text(self) -> str:
        from fastapi import WebSocketDisconnect

        raise WebSocketDisconnect(1000)


async def test_subscribing_to_a_pair_nobody_collects_is_refused(api, pool) -> None:
    """8.9. Subscribing must not quietly start collecting either — that is the decision
    the ceiling exists to keep deliberate."""
    from market_data.app import candle_feed

    socket = FakeWebSocket(symbol="US100", resolution="MINUTE")

    await candle_feed(socket, app.state.hub)

    assert socket.accepted is False
    assert socket.closed is not None
    assert "not being collected" in socket.closed[1]
    async with pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM tracked_pairs") == 0


async def test_subscribing_to_a_collected_pair_is_accepted(api, pool) -> None:
    from market_data.app import candle_feed

    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)
        await write_candles(conn, [candle(0)])
    socket = FakeWebSocket(symbol="US100", resolution="MINUTE")

    await candle_feed(socket, app.state.hub)

    assert socket.accepted is True
    assert socket.sent[0]["kind"] == "snapshot"
    assert len(socket.sent[0]["candles"]) == 1


async def test_a_subscription_is_accepted_through_the_router_too(api, pool) -> None:
    """The tests around this one call the handler themselves, which is how the handshake
    stayed broken while they all passed: the `hub` dependency asked for a `Request`, and a
    WebSocket connection is not one, so FastAPI had nothing to pass and every subscription
    failed with a 500 before the handler ran. Only the router can get that wrong, so only
    a connection made through it can notice."""
    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)
        await write_candles(conn, [candle(0)])

    sent = await _handshake("symbol=US100&resolution=MINUTE")

    assert sent[0]["type"] == "websocket.accept"
    assert json.loads(sent[1]["text"])["kind"] == "snapshot"


async def test_a_subscription_without_a_symbol_is_refused_before_the_handshake(api) -> None:
    from market_data.app import candle_feed

    socket = FakeWebSocket(resolution="MINUTE")

    await candle_feed(socket, app.state.hub)

    assert socket.accepted is False
    assert socket.closed[1] == "symbol is required"


async def test_a_subscription_with_an_unknown_resolution_is_refused(api) -> None:
    from market_data.app import candle_feed

    socket = FakeWebSocket(symbol="US100", resolution="MINUTE_2")

    await candle_feed(socket, app.state.hub)

    assert socket.accepted is False
    assert "unknown resolution" in socket.closed[1]


def _at(stamp: str) -> datetime:
    """The instant a timestamp names, however it was spelled.

    JSON renders UTC with a `Z`; comparing strings would be testing pydantic's choice of
    suffix rather than whether the archive answered with the right moment.
    """
    return datetime.fromisoformat(stamp)


async def _handshake(query: str) -> list[dict]:
    """Connect to /ws/candles through the app itself, and answer with what it sent back.

    httpx's ASGI transport speaks HTTP only, so the connection is made at the ASGI level:
    a connect, then a disconnect, which is enough to see how the handshake ended.
    """
    scope = {
        "type": "websocket",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "scheme": "ws",
        "path": "/ws/candles",
        "raw_path": b"/ws/candles",
        "query_string": query.encode(),
        "root_path": "",
        "headers": [(b"host", b"archive.test")],
        "client": ("127.0.0.1", 51234),
        "server": ("archive.test", 80),
        "subprotocols": [],
    }
    incoming = [{"type": "websocket.connect"}]
    sent: list[dict] = []

    async def receive() -> dict:
        return incoming.pop(0) if incoming else {"type": "websocket.disconnect", "code": 1000}

    async def send(message: dict) -> None:
        sent.append(message)

    await app(scope, receive, send)
    return sent


def _collector():
    """Subscribers are awaited, so `list.append` will not do."""
    received: list = []

    async def collect(message) -> None:
        received.append(message)

    return received, collect


def _settled(pool):
    async def read_settled():
        async with pool.acquire() as conn:
            from market_data.store import read_recent

            return list(await read_recent(conn, "US100", Resolution.MINUTE, 500))

    return read_settled
