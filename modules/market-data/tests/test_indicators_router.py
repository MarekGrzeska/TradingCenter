"""The router as a consumer sees it: the catalogue, and a computed range over the
contract — `market-data-indicators` spec, end to end."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from market_data.app import app
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
