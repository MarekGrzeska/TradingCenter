"""The candle-age gauge: what it reports, and what it deliberately leaves out."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from market_data.errors import GatewayUnreachable
from market_data.market_status import MarketStatus
from market_data.models import Candle, CandleSource, Resolution
from market_data.store import write_candles
from market_data.telemetry import CandleAgeGauge, compute_ages
from market_data.tracking import track

NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


class FakeInstruments:
    def __init__(self, market_open: bool | None = None) -> None:
        self.market_open = market_open

    async def is_market_open(self, symbol: str) -> bool | None:
        return self.market_open


# --- CandleAgeGauge, no I/O ---


def test_the_gauge_starts_empty() -> None:
    assert CandleAgeGauge().observe(options=None) == []


def test_the_gauge_reports_what_was_last_set() -> None:
    gauge = CandleAgeGauge()
    gauge.set({("US100", "MINUTE"): 12.5, ("GOLD", "HOUR"): 300.0})

    observations = {(o.attributes["symbol"], o.attributes["resolution"]): o.value
                     for o in gauge.observe(options=None)}

    assert observations == {("US100", "MINUTE"): 12.5, ("GOLD", "HOUR"): 300.0}


def test_a_later_set_replaces_the_earlier_one() -> None:
    gauge = CandleAgeGauge()
    gauge.set({("US100", "MINUTE"): 12.5})
    gauge.set({("GOLD", "HOUR"): 300.0})

    symbols = {o.attributes["symbol"] for o in gauge.observe(options=None)}

    assert symbols == {"GOLD"}


# --- compute_ages, against a real database ---


class _FakePool:
    """`compute_ages` only ever calls `pool.acquire()` — this wraps one already-open
    test connection so a `db`-marked test does not need testcontainers to hand out a
    second one.
    """

    def __init__(self, conn) -> None:
        self._conn = conn

    def acquire(self):
        return self


    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc_info: object) -> None:
        pass


async def _track_with_candle(conn, symbol: str, resolution: Resolution, latest: datetime) -> None:
    await track(conn, symbol, resolution, limit=20)
    await write_candles(
        conn,
        [
            Candle(
                symbol=symbol,
                resolution=resolution,
                period_start=latest,
                close=1.0,
                source=CandleSource.HISTORY,
            )
        ],
    )


@pytest.mark.db
async def test_a_stalled_pair_is_reported(db) -> None:
    latest = NOW - timedelta(minutes=10)
    await _track_with_candle(db, "US100", Resolution.MINUTE, latest)

    ages = await compute_ages(_FakePool(db), FakeInstruments(market_open=True), MarketStatus(), now=NOW)

    assert ages == {("US100", "MINUTE"): pytest.approx(600.0, abs=1.0)}


@pytest.mark.db
async def test_a_pair_whose_market_is_shut_is_excluded(db) -> None:
    # specs-level intent (design.md, group 10): the alert this feeds fires "w godzinach
    # handlu" — during trading hours. A market known to be closed contributes nothing,
    # so a Friday-to-Monday gap on an index never reads as staleness.
    latest = NOW - timedelta(days=2)
    await _track_with_candle(db, "US100", Resolution.MINUTE, latest)

    ages = await compute_ages(_FakePool(db), FakeInstruments(market_open=False), MarketStatus(), now=NOW)

    assert ages == {}


@pytest.mark.db
async def test_a_pair_with_nothing_collected_is_excluded(db) -> None:
    await track(db, "US100", Resolution.MINUTE, limit=20)

    ages = await compute_ages(_FakePool(db), FakeInstruments(market_open=True), MarketStatus(), now=NOW)

    assert ages == {}


@pytest.mark.db
async def test_a_gateway_that_will_not_say_still_reports_the_pair(db) -> None:
    # UNKNOWN, not silently dropped — an operator should see this pair, not have it
    # disappear because the gateway that would say whether to trust it is down too.
    latest = NOW - timedelta(minutes=10)
    await _track_with_candle(db, "US100", Resolution.MINUTE, latest)

    class Unreachable:
        async def is_market_open(self, symbol: str) -> bool | None:
            raise GatewayUnreachable("down")

    ages = await compute_ages(_FakePool(db), Unreachable(), MarketStatus(), now=NOW)

    assert ("US100", "MINUTE") in ages
