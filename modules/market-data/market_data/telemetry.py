"""Application Insights: the metric the most important alert stands on — the newest candle's age per
pair. An observable gauge's callback cannot await, so `refresh_loop` reads and the callback reports."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import UTC, datetime
from typing import cast

import asyncpg
from opentelemetry import metrics
from opentelemetry.metrics import CallbackOptions, Observation

from .gateway import GatewayInstruments
from .market_status import MarketStatus
from .models import Resolution
from .periods import period_length
from .tracking import (
    DELIVERY_GRACE,
    STALE_AFTER_PERIODS,
    CollectionState,
    decide_late_pairs,
    read_status,
)

log = logging.getLogger(__name__)

# Matches MarketStatus's own cache TTL — refreshing faster would only re-read a market
# status this module already has cached, for no fresher an answer.
REFRESH_INTERVAL_SECONDS = 60

# Libraries that talk at INFO about their own plumbing. `azure` is not merely noise: the exporter logs
# each upload, and that line is telemetry, uploaded, logged. 165 entries in fifteen quiet minutes.
NOISY_LOGGERS = ("azure", "httpx", "httpcore", "urllib3")

# The instrumentation records every frame `/ws/candles` sends as a dependency — a quarter-million rows in two
# weeks, measured 4 September 2026. Read once, when the FastAPI instrumentor is first imported.
EXCLUDED_URLS_SETTING = "OTEL_PYTHON_FASTAPI_EXCLUDED_URLS"
UNTRACED_PATHS = "/ws/candles"


class CandleAgeGauge:
    """The last-computed age of each pair's newest candle, for pairs whose market isn't known to be
    closed. Written by `refresh_loop`, read whenever OpenTelemetry is ready to export."""

    def __init__(self) -> None:
        self._ages: dict[tuple[str, str], float] = {}

    def set(self, ages: dict[tuple[str, str], float]) -> None:
        self._ages = ages

    def observe(self, options: CallbackOptions) -> list[Observation]:
        return [
            Observation(age, {"symbol": symbol, "resolution": resolution})
            for (symbol, resolution), age in self._ages.items()
        ]


class CandlePeriodsLateGauge:
    """The same staleness in periods of each pair's own resolution — the unit the alert uses, since one
    second threshold cannot mean the same thing for `MINUTE` and for `WEEK`."""

    def __init__(self) -> None:
        self._periods: dict[tuple[str, str], float] = {}

    def set(self, periods: dict[tuple[str, str], float]) -> None:
        self._periods = periods

    def observe(self, options: CallbackOptions) -> list[Observation]:
        return [
            Observation(value, {"symbol": symbol, "resolution": resolution})
            for (symbol, resolution), value in self._periods.items()
        ]


def periods_late(age_seconds: float, resolution: Resolution) -> float:
    """How far behind a pair's newest candle sits, past the delivery grace `tracking.py` measured.
    Floored to zero: the raw ratio would put every healthy `MINUTE` pair near four periods late."""
    behind = age_seconds - DELIVERY_GRACE.total_seconds()
    return max(0.0, behind / period_length(resolution).total_seconds())


def configure() -> None:
    """Wires up logging, and Application Insights when there is one. Called at import time in `app.py`
    before `from fastapi import FastAPI`: the instrumentation patches the class attribute."""
    configure_logging()
    if not os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        return
    os.environ.setdefault(EXCLUDED_URLS_SETTING, UNTRACED_PATHS)
    from azure.monitor.opentelemetry import configure_azure_monitor

    configure_azure_monitor()


def configure_logging() -> None:
    """Give the root logger a level and somewhere to write, because nothing else does. A deployed
    container printed uvicorn's lines and none of this module's — not silent, just never told where."""
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


def register(gauge: CandleAgeGauge, periods_gauge: CandlePeriodsLateGauge) -> None:
    meter = metrics.get_meter("market_data")
    meter.create_observable_gauge(
        "market_data.candle_age_seconds",
        callbacks=[gauge.observe],
        description=(
            "Seconds since each tracked pair's newest candle, for pairs whose market "
            "isn't known to be closed"
        ),
        unit="s",
    )
    meter.create_observable_gauge(
        "market_data.candle_age_periods",
        callbacks=[periods_gauge.observe],
        description=(
            "Periods behind each tracked pair's newest candle sits, past its delivery "
            f"grace — the module's own STALLED state fires after {STALE_AFTER_PERIODS} "
            "periods; alert-candle-age-stale fires at 3."
        ),
    )


async def compute_ages(
    pool: asyncpg.Pool,
    instruments: GatewayInstruments,
    market_status: MarketStatus,
    now: datetime | None = None,
) -> dict[tuple[str, str], float]:
    """One read of every tracked pair's newest-candle age, excluding pairs the gateway calls closed.
    `NEVER_COLLECTED` and `UNKNOWN` stay in: the second is exactly what an operator should hear about."""
    moment = now or datetime.now(UTC)
    async with pool.acquire() as conn:
        # A pool hands out a proxy that forwards to a connection without being one, so every
        # signature naming `asyncpg.Connection` is wrong by the letter and right by every method used.
        statuses = await read_status(cast(asyncpg.Connection, conn), now=moment)
    decided = await decide_late_pairs(instruments, market_status, statuses, moment)

    ages: dict[tuple[str, str], float] = {}
    for status, collection in decided:
        if collection == CollectionState.MARKET_CLOSED or status.latest_candle is None:
            continue
        ages[(status.symbol, status.resolution.value)] = (
            moment - status.latest_candle
        ).total_seconds()
    return ages


async def refresh_loop(
    pool: asyncpg.Pool,
    instruments: GatewayInstruments,
    market_status: MarketStatus,
    gauge: CandleAgeGauge,
    periods_gauge: CandlePeriodsLateGauge,
    interval: float = REFRESH_INTERVAL_SECONDS,
) -> None:
    """Runs for the life of the application, updating both gauges every `interval` seconds. A failed
    read is logged and skipped: one bad refresh should not take down half the monitoring."""
    while True:
        try:
            ages = await compute_ages(pool, instruments, market_status)
            gauge.set(ages)
            periods_gauge.set(
                {
                    (symbol, resolution): periods_late(age, Resolution(resolution))
                    for (symbol, resolution), age in ages.items()
                }
            )
        except Exception:
            log.exception("candle age refresh failed")
        await asyncio.sleep(interval)
