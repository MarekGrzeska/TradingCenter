"""The candle-age gauge: what it reports, and what it deliberately leaves out."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import pytest

from market_data import telemetry
from market_data.errors import GatewayUnreachable
from market_data.market_status import MarketStatus
from market_data.models import Candle, CandleSource, Resolution
from market_data.store import write_candles
from market_data.telemetry import CandleAgeGauge, compute_ages, periods_late
from market_data.tracking import DELIVERY_GRACE, track

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


# --- periods_late, no I/O ---


def test_a_healthy_minute_pair_reports_less_than_one_period_late() -> None:
    age = DELIVERY_GRACE.total_seconds() + 20  # well inside the measured arrival window
    assert periods_late(age, Resolution.MINUTE) < 1.0


def test_a_healthy_week_pair_reports_less_than_one_period_late() -> None:
    age = 3600.0  # an hour old, nowhere near a week's period
    assert periods_late(age, Resolution.WEEK) < 1.0


def test_a_pair_skipped_the_same_number_of_periods_reports_the_same_value() -> None:
    # Three periods behind, past the grace, whether the period is a minute or a day —
    # the whole point of the metric being in periods rather than seconds.
    minute_age = DELIVERY_GRACE.total_seconds() + 3 * 60
    day_age = DELIVERY_GRACE.total_seconds() + 3 * 86_400

    assert periods_late(minute_age, Resolution.MINUTE) == pytest.approx(3.0)
    assert periods_late(day_age, Resolution.DAY) == pytest.approx(3.0)


def test_a_candle_that_just_arrived_reports_zero_not_negative() -> None:
    assert periods_late(0.0, Resolution.MINUTE) == 0.0
    assert periods_late(DELIVERY_GRACE.total_seconds(), Resolution.HOUR_4) == 0.0


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
    # The periods gauge is derived from the same `ages` dict `refresh_loop` computes —
    # nothing to derive from means nothing reported, same as the seconds gauge.
    periods = {(s, r): periods_late(a, Resolution(r)) for (s, r), a in ages.items()}
    assert periods == {}


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


# --- logging configuration ------------------------------------------------------------


def test_configure_logging_gives_the_root_logger_a_level_and_a_handler(monkeypatch) -> None:
    """Without this the module writes into the void: uvicorn configures only its own
    three loggers, so the root keeps its default WARNING and no handler at all."""
    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [])
    monkeypatch.setattr(root, "level", logging.WARNING)

    telemetry.configure_logging()

    assert root.handlers
    assert root.level == logging.INFO


def test_configure_logging_silences_the_exporter_that_would_describe_itself(monkeypatch) -> None:
    """The Application Insights exporter logs every telemetry upload, and that line is
    itself telemetry — uploaded, then logged again. Left alone it fills the log with an
    account of its own plumbing."""
    monkeypatch.setattr(logging.getLogger(), "handlers", [])
    logging.getLogger("azure").setLevel(logging.NOTSET)

    telemetry.configure_logging()

    assert logging.getLogger("azure").level == logging.WARNING
    for name in telemetry.NOISY_LOGGERS:
        assert logging.getLogger(name).level == logging.WARNING


def test_log_level_can_be_turned_down_without_a_deploy(monkeypatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "warning")
    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [])

    telemetry.configure_logging()

    assert root.level == logging.WARNING
