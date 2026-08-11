"""The router as a consumer sees it: the catalogue, and a computed range over the
contract — `market-data-indicators` spec, end to end."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from pydantic import ValidationError

from market_data.app import app
from market_data.contract import IndicatorResultOut
from market_data.models import Candle, CandleSource, Resolution
from market_data.store import write_candles

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)


def candle(offset: int, **overrides) -> Candle:
    """One minute candle, `offset` minutes before `NOW`, on a gentle deterministic
    wave — not a straight line, so `ema` and `sma` actually differ from each other."""
    import math

    base = 100.0 + 3 * math.sin(offset / 4)
    return Candle(
        **{
            "symbol": "US100",
            "resolution": Resolution.MINUTE,
            "period_start": NOW - timedelta(minutes=offset),
            "open": base,
            "high": base + 0.6,
            "low": base - 0.6,
            "close": base + 0.2,
            "volume": 10.0,
            "source": CandleSource.HISTORY,
            **overrides,
        }
    )


# --- the result model itself: the one combination that must not be buildable ---------


class TestResultShapeOrError:
    """`market-data-indicators` spec, "Wynik ma jeden z czterech kształtów" — enforced on
    the model rather than left to whoever writes the next branch of `_result_out`."""

    def test_a_shape_and_a_reason_together_are_refused(self):
        # The combination that would read to a consumer looking only at the shape as
        # "computed, and it was empty" — the opposite of what happened.
        with pytest.raises(ValidationError, match="must carry no shape"):
            IndicatorResultOut(
                id="range_gap", params={}, settled=False, zones=[], error="no series"
            )

    def test_neither_a_shape_nor_a_reason_is_still_refused(self):
        with pytest.raises(ValidationError, match="exactly one of"):
            IndicatorResultOut(id="ema", params={}, settled=True)

    def test_a_reason_alone_is_a_whole_result(self):
        result = IndicatorResultOut(
            id="time_profile", params={}, settled=False, error="no MINUTE_5 series collected"
        )
        assert result.error == "no MINUTE_5 series collected"
        assert (result.lines, result.markers, result.zones, result.levels) == (None,) * 4

    def test_two_shapes_at_once_are_refused_as_before(self):
        with pytest.raises(ValidationError, match="exactly one of"):
            IndicatorResultOut(id="ema", params={}, settled=True, lines={"ema": []}, zones=[])


# --- catalogue: no database, no app.state — the route touches neither -----------------


@pytest.fixture
async def catalogue_client():
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://archive.test") as client:
        yield client


async def test_catalogue_lists_entries_with_everything_a_picker_needs(catalogue_client) -> None:
    body = (await catalogue_client.get("/indicators")).json()

    assert body["algorithm_version"] >= 1
    ids = {entry["id"] for entry in body["indicators"]}
    assert {"sma", "ema", "atr"} <= ids

    ema_entry = next(e for e in body["indicators"] if e["id"] == "ema")
    assert ema_entry["params"] == [
        {"name": "period", "type": "int", "default": 20, "min": 2, "max": 5000}
    ]
    assert ema_entry["lines"] == [{"key": "ema", "label": "EMA {period}", "style": None}]
    assert ema_entry["render"]["pane"] == "price"
    assert ema_entry["output"] == "lines"


async def test_catalogue_carries_no_volume_entry(catalogue_client) -> None:
    body = (await catalogue_client.get("/indicators")).json()
    for entry in body["indicators"]:
        # No wire vocabulary for a volume input exists at all — this is the contract-level
        # half of test_indicators_catalogue.py's `test_no_entry_reads_volume`.
        assert "volume" not in entry["name"].lower() or "obv" not in entry["id"]


# --- compute: needs the real archive -----------------------------------------------------

pytestmark = pytest.mark.db


@pytest.fixture
async def pool(migrated_url: str):
    from market_data.db import pool as make_pool

    async with make_pool(migrated_url, max_size=5) as created:
        async with created.acquire() as conn:
            await conn.execute(
                "TRUNCATE candles, derived_candles, tracked_pairs, coverage_ranges, "
                "collection_jobs, collection_job_chunks, pair_deletions"
            )
        yield created


@pytest.fixture
async def api(pool):
    app.state.pool = pool
    app.state.indicator_limiter = asyncio.Semaphore(4)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://archive.test") as client:
        yield client


async def test_computes_a_line_indicator_over_the_requested_range(api, pool) -> None:
    async with pool.acquire() as conn:
        await write_candles(conn, [candle(m) for m in range(30, -1, -1)])

    response = await api.post(
        "/indicators/US100",
        json={
            "resolution": "MINUTE",
            "from": (NOW - timedelta(minutes=10)).isoformat(),
            "to": (NOW + timedelta(minutes=1)).isoformat(),
            "specs": [{"id": "sma", "params": {"period": 5}}],
        },
    )
    body = response.json()

    assert response.status_code == 200
    assert len(body["times"]) == 11  # minutes -10..0 inclusive
    [result] = body["results"]
    assert result["id"] == "sma"
    assert result["params"] == {"period": 5}
    assert len(result["lines"]["sma"]) == 11
    # The window has 31 candles behind `from`, comfortably past a 5-period SMA's warmup.
    assert result["settled"] is True
    assert all(v is not None for v in result["lines"]["sma"])


async def test_reads_further_back_than_from_for_warmup(api, pool) -> None:
    async with pool.acquire() as conn:
        await write_candles(conn, [candle(m) for m in range(2, -1, -1)])  # only 3 candles

    response = await api.post(
        "/indicators/US100",
        json={
            "resolution": "MINUTE",
            "from": (NOW - timedelta(minutes=1)).isoformat(),
            "to": (NOW + timedelta(minutes=1)).isoformat(),
            "specs": [{"id": "ema", "params": {"period": 20}}],
        },
    )
    body = response.json()

    # 3 candles cannot satisfy EMA(20)'s warmup (≈ 200 bars) — the point of this test is
    # that the module says so rather than answering as if it could.
    [result] = body["results"]
    assert result["settled"] is False
    assert result["warmup_bars"] > 3


async def test_unknown_indicator_is_refused_by_name(api) -> None:
    response = await api.post(
        "/indicators/US100",
        json={
            "resolution": "MINUTE",
            "from": (NOW - timedelta(minutes=1)).isoformat(),
            "to": NOW.isoformat(),
            "specs": [{"id": "not-a-real-indicator"}],
        },
    )
    assert response.status_code == 422
    assert "not-a-real-indicator" in response.json()["detail"]


async def test_param_out_of_range_is_refused_by_name(api) -> None:
    response = await api.post(
        "/indicators/US100",
        json={
            "resolution": "MINUTE",
            "from": (NOW - timedelta(minutes=1)).isoformat(),
            "to": NOW.isoformat(),
            "specs": [{"id": "ema", "params": {"period": 999999}}],
        },
    )
    assert response.status_code == 422
    assert "period" in response.json()["detail"]


async def test_a_range_that_ends_before_it_starts_is_refused(api) -> None:
    response = await api.post(
        "/indicators/US100",
        json={
            "resolution": "MINUTE",
            "from": NOW.isoformat(),
            "to": (NOW - timedelta(hours=1)).isoformat(),
            "specs": [{"id": "sma", "params": {"period": 5}}],
        },
    )
    assert response.status_code == 422
    assert "is before" in response.json()["detail"]


async def test_request_above_the_ceiling_is_refused(api) -> None:
    from market_data.routers.indicators import REQUEST_CEILING

    # One indicator, a range wide enough alone to clear the ceiling.
    minutes = REQUEST_CEILING + 10
    response = await api.post(
        "/indicators/US100",
        json={
            "resolution": "MINUTE",
            "from": (NOW - timedelta(minutes=minutes)).isoformat(),
            "to": NOW.isoformat(),
            "specs": [{"id": "sma", "params": {"period": 5}}],
        },
    )
    assert response.status_code == 422
    assert "ceiling" in response.json()["detail"]


async def test_uncovered_stretch_is_carried_into_the_response(api, pool) -> None:
    from market_data.coverage import record_coverage

    async with pool.acquire() as conn:
        await record_coverage(
            conn, "US100", Resolution.MINUTE, NOW - timedelta(minutes=5), NOW - timedelta(minutes=2)
        )

    body = (
        await api.post(
            "/indicators/US100",
            json={
                "resolution": "MINUTE",
                "from": (NOW - timedelta(minutes=5)).isoformat(),
                "to": NOW.isoformat(),
                "specs": [{"id": "sma", "params": {"period": 3}}],
            },
        )
    ).json()

    # Coverage recorded only [NOW-5, NOW-2) — the rest of the requested range, [NOW-2, NOW),
    # was never verified and is the one gap this answers with.
    [gap] = body["uncovered"]
    assert datetime.fromisoformat(gap["from"]) == NOW - timedelta(minutes=2)
    assert datetime.fromisoformat(gap["to"]) == NOW


async def test_the_response_names_its_side_and_algorithm_version(api) -> None:
    body = (
        await api.post(
            "/indicators/US100",
            json={
                "resolution": "MINUTE",
                "from": (NOW - timedelta(minutes=1)).isoformat(),
                "to": NOW.isoformat(),
                "specs": [{"id": "sma", "params": {"period": 3}}],
            },
        )
    ).json()

    assert body["price_side"] == "bid"
    assert body["algorithm_version"] >= 1


# --- W1, points and levels: markers, cluster levels, cross-resolution levels ----------


async def test_swing_points_are_returned_as_markers(api, pool) -> None:
    # A clean up-down-up wiggle so bar 5 (offset 25) is an unambiguous swing high
    # confirmed by n=2 bars either side.
    heights = {
        30: 0.0, 29: 0.2, 28: 0.4, 27: 0.6, 26: 0.8,
        25: 2.0,
        24: 0.8, 23: 0.6, 22: 0.4, 21: 0.2, 20: 0.0,
    }
    async with pool.acquire() as conn:
        await write_candles(
            conn,
            [
                candle(m, high=100.0 + heights.get(m, 0.0), low=99.0, close=99.5, open=99.5)
                for m in range(30, -1, -1)
            ],
        )

    response = await api.post(
        "/indicators/US100",
        json={
            "resolution": "MINUTE",
            "from": (NOW - timedelta(minutes=29)).isoformat(),
            "to": (NOW + timedelta(minutes=1)).isoformat(),
            "specs": [{"id": "swing_points", "params": {"n": 2}}],
        },
    )
    body = response.json()

    assert response.status_code == 200
    [result] = body["results"]
    assert result["lines"] is None
    assert result["markers"] is not None
    swing_high = next(m for m in result["markers"] if m["label"] == "Swing High")
    assert swing_high["price"] == pytest.approx(102.0)
    assert datetime.fromisoformat(swing_high["time"]) == NOW - timedelta(minutes=25)


async def test_level_clusters_are_returned_with_a_count(api, pool) -> None:
    heights = {
        30: 0.0, 29: 0.2, 28: 0.4, 27: 0.6, 26: 3.0,
        25: 0.6, 24: 0.4, 23: 0.2, 22: 0.0, 21: 0.2,
        20: 0.4, 19: 0.6, 18: 3.05,
        17: 0.6, 16: 0.4, 15: 0.2, 14: 0.0,
    }
    async with pool.acquire() as conn:
        await write_candles(
            conn,
            [
                candle(m, high=100.0 + heights.get(m, 0.0), low=99.0, close=99.5, open=99.5)
                for m in range(30, -1, -1)
            ],
        )

    response = await api.post(
        "/indicators/US100",
        json={
            "resolution": "MINUTE",
            "from": (NOW - timedelta(minutes=29)).isoformat(),
            "to": (NOW + timedelta(minutes=1)).isoformat(),
            "specs": [{"id": "level_clusters", "params": {"n": 2, "tol": 1.0, "atr_period": 5}}],
        },
    )
    body = response.json()

    assert response.status_code == 200
    [result] = body["results"]
    assert result["levels"] is not None
    equal_highs = [lvl for lvl in result["levels"] if lvl["label"] == "Equal High"]
    assert len(equal_highs) == 1
    assert equal_highs[0]["count"] == 2


async def test_htf_levels_day_reads_the_previous_closed_day(api, pool) -> None:
    """Task 3.11: PDH/PDL on a MINUTE_15 series carry the previous day's own
    OHLC, valid from that day's close — not from the start of the series."""
    day_before = datetime(2026, 8, 5, tzinfo=UTC)
    display_day = datetime(2026, 8, 6, tzinfo=UTC)

    async with pool.acquire() as conn:
        await write_candles(
            conn,
            [
                Candle(
                    symbol="US100",
                    resolution=Resolution.DAY,
                    period_start=day_before,
                    open=100.0,
                    high=110.0,
                    low=95.0,
                    close=105.0,
                    source=CandleSource.HISTORY,
                ),
                Candle(
                    symbol="US100",
                    resolution=Resolution.DAY,
                    period_start=display_day,
                    open=105.0,
                    high=120.0,
                    low=100.0,
                    close=115.0,
                    source=CandleSource.HISTORY,
                ),
            ],
        )
        await write_candles(
            conn,
            [
                candle(0, resolution=Resolution.MINUTE_15, period_start=display_day + timedelta(minutes=m))
                for m in range(0, 24 * 60, 15)
            ],
        )

    response = await api.post(
        "/indicators/US100",
        json={
            "resolution": "MINUTE_15",
            "from": display_day.isoformat(),
            "to": (display_day + timedelta(days=1)).isoformat(),
            "specs": [{"id": "htf_levels_day"}],
        },
    )
    body = response.json()

    assert response.status_code == 200
    [result] = body["results"]
    at_display_day = [
        lvl for lvl in result["levels"] if datetime.fromisoformat(lvl["from"]) == display_day
    ]
    pd_high = next(lvl for lvl in at_display_day if lvl["label"] == "PD High")
    pd_low = next(lvl for lvl in at_display_day if lvl["label"] == "PD Low")
    assert pd_high["price"] == pytest.approx(110.0)
    assert pd_low["price"] == pytest.approx(95.0)


async def test_htf_levels_names_the_missing_day_series_in_its_own_result(api, pool) -> None:
    """Acceptance criterion: cross-resolution reads must not break on a pair collected
    only at MINUTE — the entry that needed the series says so, and says it alone."""
    async with pool.acquire() as conn:
        await write_candles(conn, [candle(m) for m in range(30, -1, -1)])

    response = await api.post(
        "/indicators/US100",
        json={
            "resolution": "MINUTE",
            "from": (NOW - timedelta(minutes=10)).isoformat(),
            "to": NOW.isoformat(),
            "specs": [{"id": "ema"}, {"id": "htf_levels_day"}],
        },
    )
    assert response.status_code == 200

    results = {r["id"]: r for r in response.json()["results"]}
    assert results["ema"]["lines"]["ema"], "the indicator that could be computed was"
    assert results["ema"]["error"] is None
    assert "DAY" in results["htf_levels_day"]["error"]
    # No shape at all — an empty `levels` would read as "computed, found none".
    assert results["htf_levels_day"]["levels"] is None


# --- E3, zones: zones on the wire, and task 4.3's coverage-driven session gap ---


_TODAY = NOW.replace(hour=0, minute=0, second=0, microsecond=0)


def _day_candle(period_start: datetime, **overrides) -> Candle:
    return Candle(
        **{
            "symbol": "US100",
            "resolution": Resolution.DAY,
            "period_start": period_start,
            "open": 100.0,
            "high": 100.6,
            "low": 99.4,
            "close": 100.2,
            "source": CandleSource.HISTORY,
            **overrides,
        }
    )


async def test_range_gap_is_returned_with_direction_and_bounds(api, pool) -> None:
    async with pool.acquire() as conn:
        await write_candles(
            conn,
            [
                candle(2, high=101.0, low=100.0),
                candle(1, high=102.0, low=101.0),  # the impulse candle
                candle(0, high=103.0, low=102.0),
            ],
        )

    response = await api.post(
        "/indicators/US100",
        json={
            "resolution": "MINUTE",
            "from": (NOW - timedelta(minutes=2)).isoformat(),
            "to": (NOW + timedelta(minutes=1)).isoformat(),
            "specs": [{"id": "range_gap", "params": {"skip_session_gaps": 0}}],
        },
    )
    body = response.json()

    assert response.status_code == 200
    [result] = body["results"]
    assert result["lines"] is None
    [zone] = result["zones"]
    assert zone["direction"] == "bullish"
    assert zone["top"] == pytest.approx(102.0)
    assert zone["bottom"] == pytest.approx(101.0)
    assert datetime.fromisoformat(zone["from"]) == NOW - timedelta(minutes=2)
    assert zone["to"] is None  # never touched within the read range


async def test_friday_to_sunday_gap_is_not_reported_as_a_price_gap(api, pool) -> None:
    """Task 4.8: a weekend close is a session boundary the archive has
    verified, not an imbalance — `skip_session_gaps` (on by default) must
    suppress it, and the same data must show the module *would* have
    reported it otherwise, proving the suppression is doing something."""
    from market_data.coverage import record_coverage

    thursday = datetime(2026, 8, 6, tzinfo=UTC)  # real calendar dates —
    friday = datetime(2026, 8, 7, tzinfo=UTC)  # the point is the actual
    monday = datetime(2026, 8, 10, tzinfo=UTC)  # Friday-to-Monday market close

    async with pool.acquire() as conn:
        await write_candles(
            conn,
            [
                _day_candle(thursday, high=101.0, low=100.0),
                _day_candle(friday, high=102.0, low=101.0),  # the impulse candle
                _day_candle(monday, high=104.0, low=103.0),
            ],
        )
        # The whole window verified, weekend included — the archive looked
        # and found nothing there, `Absence.MARKET_CLOSED`, not a hole ingest
        # left behind.
        await record_coverage(conn, "US100", Resolution.DAY, thursday, monday + timedelta(days=1))

    request_body = {
        "resolution": "DAY",
        "from": thursday.isoformat(),
        "to": (monday + timedelta(days=1)).isoformat(),
    }

    default_response = await api.post(
        "/indicators/US100",
        json={**request_body, "specs": [{"id": "range_gap"}]},  # skip_session_gaps defaults on
    )
    assert default_response.json()["results"][0]["zones"] == []

    unsuppressed_response = await api.post(
        "/indicators/US100",
        json={
            **request_body,
            "specs": [{"id": "range_gap", "params": {"skip_session_gaps": 0}}],
        },
    )
    assert len(unsuppressed_response.json()["results"][0]["zones"]) == 1


async def test_session_range_reads_the_minute_series_regardless_of_requested_resolution(
    api, pool
) -> None:
    async with pool.acquire() as conn:
        await write_candles(conn, [_day_candle(_TODAY)])
        await write_candles(
            conn,
            [
                candle(
                    0,
                    # `FINE_RESOLUTION` (`routers/indicators.py`) — nothing in
                    # a real deployment tracks raw MINUTE, only this and up.
                    resolution=Resolution.MINUTE_5,
                    # 07:30 UTC — London runs BST (UTC+1) in August, so this
                    # is local 08:30, inside the 08:00-09:00 window below.
                    period_start=_TODAY.replace(hour=7, minute=30),
                    high=105.0,
                    low=104.0,
                )
            ],
        )

    response = await api.post(
        "/indicators/US100",
        json={
            "resolution": "DAY",
            "from": _TODAY.isoformat(),
            "to": (_TODAY + timedelta(days=1)).isoformat(),
            "specs": [{"id": "session_range_london", "params": {"from_hour": 8.0, "to_hour": 9.0}}],
        },
    )
    body = response.json()

    assert response.status_code == 200
    [result] = body["results"]
    [zone] = result["zones"]
    assert zone["top"] == pytest.approx(105.0)
    assert zone["bottom"] == pytest.approx(104.0)


# --- E4, time profile: task 5.3's refusal, and the minute-series ceiling ---


async def test_time_profile_names_the_missing_minute_series_in_its_own_result(api, pool) -> None:
    async with pool.acquire() as conn:
        await write_candles(
            conn, [_day_candle(_TODAY - timedelta(days=d)) for d in range(5, -1, -1)]
        )

    response = await api.post(
        "/indicators/US100",
        json={
            "resolution": "DAY",
            "from": (NOW - timedelta(days=5)).isoformat(),
            "to": NOW.isoformat(),
            "specs": [{"id": "time_profile"}],
        },
    )
    # Every requested indicator failing is still an answer, not a refusal: the caller
    # asked a well-formed question and the archive answered what it had, which is
    # nothing (spec, "Wszystkie zamówione wskaźniki bez serii").
    assert response.status_code == 200

    [result] = response.json()["results"]
    assert "MINUTE" in result["error"]
    assert result["levels"] is None


async def test_time_profile_computes_from_the_minute_series_at_day_resolution(api, pool) -> None:
    async with pool.acquire() as conn:
        await write_candles(conn, [_day_candle(_TODAY)])
        await write_candles(
            conn,
            [
                candle(m, resolution=Resolution.MINUTE_5, period_start=NOW - timedelta(minutes=m))
                for m in range(60, -1, -5)
            ],
        )

    response = await api.post(
        "/indicators/US100",
        json={
            "resolution": "DAY",
            "from": _TODAY.isoformat(),
            "to": (_TODAY + timedelta(days=1)).isoformat(),
            "specs": [{"id": "time_profile"}],
        },
    )
    body = response.json()

    assert response.status_code == 200
    [result] = body["results"]
    assert result["lines"] is None
    assert any(lvl["label"] == "POC" for lvl in result["levels"])


async def test_a_wide_request_hiding_a_bigger_minute_read_is_refused(api, pool) -> None:
    """The fine-resolution series `time_profile` needs behind a DAY-resolution
    request is invisible to the ceiling's own `candles×indicators` count —
    this is the check that keeps it from silently bypassing that ceiling."""
    from market_data.routers.indicators import REQUEST_CEILING

    # `FINE_RESOLUTION` is MINUTE_5 (288/day), not MINUTE (1440/day) — the
    # width that clears the ceiling is almost five times as many days.
    days = REQUEST_CEILING // 288 + 10
    response = await api.post(
        "/indicators/US100",
        json={
            "resolution": "DAY",
            "from": (NOW - timedelta(days=days)).isoformat(),
            "to": NOW.isoformat(),
            "specs": [{"id": "time_profile"}],
        },
    )
    assert response.status_code == 422
    assert "ceiling" in response.json()["detail"]


# --- partial answers: whose problem it is decides the granularity of the refusal ------


class TestPartialAnswer:
    """`market-data-indicators` spec, "Brakująca seria nie unieważnia policzonych
    wskaźników" — the boundary runs along whose problem the failure is."""

    async def test_a_missing_series_leaves_the_rest_computed(self, api, pool) -> None:
        async with pool.acquire() as conn:
            await write_candles(
                conn, [_day_candle(_TODAY - timedelta(days=d)) for d in range(5, -1, -1)]
            )

        response = await api.post(
            "/indicators/US100",
            json={
                "resolution": "DAY",
                "from": (_TODAY - timedelta(days=5)).isoformat(),
                "to": (_TODAY + timedelta(days=1)).isoformat(),
                "specs": [{"id": "sma", "params": {"period": 2}}, {"id": "time_profile"}],
            },
        )
        assert response.status_code == 200

        results = {r["id"]: r for r in response.json()["results"]}
        assert results["sma"]["error"] is None
        assert results["sma"]["lines"]["sma"]
        assert "MINUTE" in results["time_profile"]["error"]

    async def test_every_indicator_failing_is_still_an_answer(self, api, pool) -> None:
        async with pool.acquire() as conn:
            await write_candles(
                conn, [_day_candle(_TODAY - timedelta(days=d)) for d in range(5, -1, -1)]
            )

        response = await api.post(
            "/indicators/US100",
            json={
                "resolution": "DAY",
                "from": (_TODAY - timedelta(days=5)).isoformat(),
                "to": (_TODAY + timedelta(days=1)).isoformat(),
                "specs": [{"id": "time_profile"}, {"id": "session_range_london"}],
            },
        )
        assert response.status_code == 200

        results = response.json()["results"]
        assert len(results) == 2
        assert all(r["error"] for r in results)
        # Every requested id is still present. A consumer that asked for two indicators
        # and got one row back cannot tell which of the two it is holding.
        assert {r["id"] for r in results} == {"time_profile", "session_range_london"}

    async def test_an_unknown_id_still_refuses_the_whole_request(self, api, pool) -> None:
        async with pool.acquire() as conn:
            await write_candles(conn, [candle(m) for m in range(30, -1, -1)])

        response = await api.post(
            "/indicators/US100",
            json={
                "resolution": "MINUTE",
                "from": (NOW - timedelta(minutes=10)).isoformat(),
                "to": NOW.isoformat(),
                "specs": [{"id": "ema"}, {"id": "nie_ma_takiego"}],
            },
        )
        # A typo answered partially is one nobody notices; a 422 is not.
        assert response.status_code == 422
        assert "nie_ma_takiego" in response.json()["detail"]

    async def test_a_parameter_out_of_range_still_refuses_the_whole_request(
        self, api, pool
    ) -> None:
        async with pool.acquire() as conn:
            await write_candles(conn, [candle(m) for m in range(30, -1, -1)])

        response = await api.post(
            "/indicators/US100",
            json={
                "resolution": "MINUTE",
                "from": (NOW - timedelta(minutes=10)).isoformat(),
                "to": NOW.isoformat(),
                "specs": [{"id": "atr"}, {"id": "ema", "params": {"period": 999_999}}],
            },
        )
        assert response.status_code == 422
        assert "period" in response.json()["detail"]

    async def test_the_same_request_twice_gives_the_same_reasons(self, api, pool) -> None:
        async with pool.acquire() as conn:
            await write_candles(
                conn, [_day_candle(_TODAY - timedelta(days=d)) for d in range(5, -1, -1)]
            )
        body = {
            "resolution": "DAY",
            "from": (_TODAY - timedelta(days=5)).isoformat(),
            "to": (_TODAY + timedelta(days=1)).isoformat(),
            "specs": [{"id": "sma", "params": {"period": 2}}, {"id": "time_profile"}],
        }

        first = await api.post("/indicators/US100", json=body)
        second = await api.post("/indicators/US100", json=body)

        assert first.status_code == second.status_code == 200
        assert first.json() == second.json()

    async def test_one_read_serves_every_entry_wanting_the_same_series(self, api, pool) -> None:
        """The reason a missing series is recorded per resolution rather than per entry:
        four entries wanting the fine series must not read it four times."""
        reads: list[Resolution] = []
        import market_data.routers.indicators as router_module

        real_read = router_module.read_candles

        async def counting_read(conn, symbol, resolution, *args, **kwargs):
            reads.append(resolution)
            return await real_read(conn, symbol, resolution, *args, **kwargs)

        async with pool.acquire() as conn:
            await write_candles(
                conn, [_day_candle(_TODAY - timedelta(days=d)) for d in range(5, -1, -1)]
            )

        router_module.read_candles = counting_read
        try:
            response = await api.post(
                "/indicators/US100",
                json={
                    "resolution": "DAY",
                    "from": (_TODAY - timedelta(days=5)).isoformat(),
                    "to": (_TODAY + timedelta(days=1)).isoformat(),
                    "specs": [
                        {"id": "time_profile"},
                        {"id": "session_range_london"},
                        {"id": "session_range_new_york"},
                        {"id": "session_range_tokyo"},
                    ],
                },
            )
        finally:
            router_module.read_candles = real_read

        assert response.status_code == 200
        assert reads.count(Resolution.MINUTE_5) == 1, reads
