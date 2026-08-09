"""Application Insights: the metric the most important alert stands on.

Only the newest candle's age, per pair, and only for pairs a shut market would make it
noisy to complain about — a market closed since Friday leaves its "newest candle" a
Monday morning old, and that is the schedule, not staleness. `collection_state` already
tells the two apart (`STALLED` vs `MARKET_CLOSED`); this reads the same distinction
rather than inventing a second one.

An OpenTelemetry observable gauge's callback runs synchronously, on the exporter's own
schedule — it cannot itself await a database query. So the read happens in
`refresh_loop`, on its own schedule, and the callback only reports what that loop last
found. Unset `APPLICATIONINSIGHTS_CONNECTION_STRING` (every local run) is not a special
case here: `configure()` is simply never called, and `opentelemetry.metrics.get_meter`
falls back to its built-in no-op provider, so every call below still succeeds — it just
reports nothing.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import UTC, datetime

import asyncpg
from opentelemetry import metrics
from opentelemetry.metrics import CallbackOptions, Observation

from .gateway import GatewayInstruments
from .market_status import MarketStatus
from .tracking import CollectionState, decide_late_pairs, read_status

log = logging.getLogger(__name__)

# Matches MarketStatus's own cache TTL — refreshing faster would only re-read a market
# status this module already has cached, for no fresher an answer.
REFRESH_INTERVAL_SECONDS = 60


class CandleAgeGauge:
    """The last-computed age, in seconds, of each pair's newest candle — for pairs whose
    market isn't known to be closed. Written by `refresh_loop`; read by `observe`, which
    OpenTelemetry calls whenever it is ready to export, not on any schedule this class
    controls.
    """

    def __init__(self) -> None:
        self._ages: dict[tuple[str, str], float] = {}

    def set(self, ages: dict[tuple[str, str], float]) -> None:
        self._ages = ages

    def observe(self, options: CallbackOptions) -> list[Observation]:
        return [
            Observation(age, {"symbol": symbol, "resolution": resolution})
            for (symbol, resolution), age in self._ages.items()
        ]


def configure() -> None:
    """Wires up logging, and Application Insights when there is one to wire to. Called
    once, from `lifespan`, before anything registers a metric.
    """
    configure_logging()
    if not os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        return
    from azure.monitor.opentelemetry import configure_azure_monitor

    configure_azure_monitor()


def configure_logging() -> None:
    """Give the root logger a level and somewhere to write, because nothing else does.

    Uvicorn configures its own three loggers and leaves the root alone, so a deployed
    container printed `GET /pairs 200` and not one line this module wrote: the root
    logger's default level is WARNING, and it had no handler regardless. Application
    Insights was no better — the handler Azure Monitor attaches to the root logger is
    gated by that same level, so `INFO` never reached it either.

    What that cost, concretely: a collection job that never started looked exactly like
    one running quietly, because `chunk N done: wrote X candles` had nowhere to go. The
    module was not silent — nobody had told it where to speak.

    `LOG_LEVEL` overrides, for turning the volume down without a deploy. `basicConfig` is
    a no-op if the root logger already has a handler, which is the right behaviour: a
    caller who configured logging themselves keeps their configuration.
    """
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )


def register(gauge: CandleAgeGauge) -> None:
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


async def compute_ages(
    pool: asyncpg.Pool,
    instruments: GatewayInstruments,
    market_status: MarketStatus,
    now: datetime | None = None,
) -> dict[tuple[str, str], float]:
    """One read of every tracked pair's newest-candle age, keyed by (symbol, resolution),
    excluding pairs the gateway says are `MARKET_CLOSED`.

    A pair still `NEVER_COLLECTED` or `UNKNOWN` is included: the first has no candle to
    age (nothing to observe), and the second is exactly the case an operator should be
    told about rather than have silently excluded.
    """
    moment = now or datetime.now(UTC)
    async with pool.acquire() as conn:
        statuses = await read_status(conn, now=moment)
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
    interval: float = REFRESH_INTERVAL_SECONDS,
) -> None:
    """Runs for the life of the application, updating `gauge` every `interval` seconds.

    A failed read is logged and skipped rather than raised — one bad refresh should not
    take down the loop that is, itself, half of the monitoring for everything else.
    """
    while True:
        try:
            gauge.set(await compute_ages(pool, instruments, market_status))
        except Exception:
            log.exception("candle age refresh failed")
        await asyncio.sleep(interval)
