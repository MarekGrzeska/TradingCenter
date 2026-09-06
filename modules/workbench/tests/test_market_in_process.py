"""The candle archive as a package of this process: mounted whole under `/market`, its stream kept out of the trace
by the host, and read by the strategy platform through the archive's own application rather than over the network."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from starlette.routing import Mount

import market_data.telemetry
from market_data.app import create_app as create_market_app
from market_data.config import Settings as MarketSettings
from market_data.hub import Hub
from market_data.market_status import MarketStatus
from market_data.models import Candle, CandleSource, PriceSide, Resolution
from market_data.store import write_candles
from market_data.tickets import TicketStore
from market_data.tracking import track
from strategy.archive import Archive
from workbench import app as host
from workbench.archive_client import archive_client

from .market.fakes import FakeIngest, FakeInstruments, FakeJobRunner


def test_the_archive_is_mounted_whole_and_its_stream_is_kept_out_of_the_trace() -> None:
    mounts = {route.path for route in host.app.routes if isinstance(route, Mount)}
    assert "/market" in mounts
    # The package says which of its paths is the stream; the host says where the package is. The instrumentor
    # reads the environment once, so the host has to have said it before it configured telemetry.
    assert host.UNTRACED_URLS == "/market" + market_data.telemetry.UNTRACED_PATH
    assert host.UNTRACED_URLS in os.environ["OTEL_PYTHON_FASTAPI_EXCLUDED_URLS"]


@pytest.mark.db
async def test_the_strategy_platform_reads_the_archive_in_this_process_and_the_network_is_refused(
    market_migrated_url: str,
) -> None:
    """One integration test that the pairing works (CLAUDE.md, rule 5): the platform's client sees the candle the
    archive holds, through the archive's route record set to refuse every application — and a client that is not
    this process meets that refusal."""
    from tc_runtime.db import pool as make_pool

    period_start = datetime.now(UTC).replace(second=0, microsecond=0)
    period_start -= timedelta(minutes=period_start.minute % 5 + 5)
    async with make_pool(market_migrated_url, max_size=2) as pool:
        async with pool.acquire() as conn:
            from .market.conftest import TABLES

            await conn.execute(f"TRUNCATE {', '.join(TABLES)}")
            await track(conn, "US100", Resolution.MINUTE_5, limit=160)
            await write_candles(
                conn,
                [
                    Candle(
                        symbol="US100",
                        resolution=Resolution.MINUTE_5,
                        period_start=period_start,
                        open=1.0,
                        high=2.0,
                        low=0.5,
                        close=1.5,
                        volume=None,
                        price_side=PriceSide.BID,
                        source=CandleSource.HISTORY,
                        forming=False,
                    )
                ],
            )

        market_app = create_market_app()
        market_app.state.pool = pool
        market_app.state.hub = Hub()
        market_app.state.settings = MarketSettings(
            database_url="postgresql://localhost:5432/test?sslmode=require",
            database_user="test-user",
            gateway_api_key="test-gateway-key",
            require_authenticated_principal=True,
            rest_caller_application_ids="",
            _env_file=None,
        )
        market_app.state.instruments = FakeInstruments()
        market_app.state.ingest = FakeIngest()
        market_app.state.market_status = MarketStatus()
        market_app.state.job_runner = FakeJobRunner()
        market_app.state.tickets = TicketStore(timedelta(seconds=30))

        async with archive_client(market_app) as client:
            assert await Archive("", client).last_closed_bar("US100", "MINUTE_5") == period_start

        transport = httpx.ASGITransport(app=market_app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://market.test") as network:
            refused = await network.get("/candles/US100", params={"resolution": "MINUTE_5"})
        assert refused.status_code == 401
