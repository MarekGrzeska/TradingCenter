"""The one thing in this module that could not be settled by reasoning (5.1).

Derived resolutions are computed from the minute series, and that is only sound if the
period boundary this module floors to is the boundary the provider uses. `HOUR_4` is the
one where a guess is plausible and wrong in a way nothing would catch: the arithmetic
anchors on the epoch, which is UTC midnight, and a provider anchoring on a venue's open
instead would hand back candles that are the right length, the right shape and offset by
hours. Every one of them would look correct on a chart.

So it is measured. These tests read through a running `capital-gateway` against the demo
API, take the provider's own `HOUR_4` candles and the minute series underneath them, and
compare a derivation against the observation for the same periods.

Skipped unless `--run-live` is passed and a gateway is listening. Read-only, and shallow:
a day of minutes for one pair, which is what the change's own constraint on the apply
phase allows.

    uv run uvicorn capital_gateway.app:app --port 8010    # in modules/capital-gateway
    uv run pytest -m live --run-live
"""

from __future__ import annotations

import os
from collections import Counter
from datetime import timedelta

import asyncpg
import httpx
import pytest

from market_data.gateway import GatewayHistory, http_client
from market_data.models import Resolution
from market_data.rollups import bucket_start, read_derived, refresh
from market_data.store import write_candles

pytestmark = [pytest.mark.live, pytest.mark.db]

GATEWAY_URL = os.environ.get("MARKET_DATA_GATEWAY_URL", "http://localhost:8010")

# Bitcoin trades every hour of every day, so a four-hour period is never cut short by a
# session boundary and a mismatch cannot be blamed on the market being shut. US100 is
# checked alongside it precisely because it *does* have sessions: if the anchor were the
# venue's open rather than the clock, the two would disagree with each other.
CONTINUOUS = "BTCUSD"
SESSION_BOUND = "US100"

# A day: six whole four-hour periods, and two requests through the gateway's pager.
MINUTES = 1_440
FOUR_HOUR_BARS = 12

# Prices carry a couple of decimals and cross a float boundary twice on the way here, so
# equality is checked to a hair rather than to the bit.
TOLERANCE = 1e-6


@pytest.fixture
async def gateway():
    async with http_client() as client:
        try:
            await client.get(f"{GATEWAY_URL}/capabilities", timeout=5)
        except httpx.RequestError as err:
            pytest.skip(f"no capital-gateway at {GATEWAY_URL}: {err}")
        yield GatewayHistory(GATEWAY_URL, client)


@pytest.mark.parametrize("symbol", [CONTINUOUS, SESSION_BOUND])
async def test_the_provider_anchors_four_hour_candles_on_utc_midnight(
    gateway: GatewayHistory, symbol: str
) -> None:
    """The claim, at its cheapest: where do the provider's own periods start?"""
    page = await gateway.history(symbol, Resolution.HOUR_4, FOUR_HOUR_BARS)
    assert page.candles, f"the demo API returned no HOUR_4 candles for {symbol}"

    starts = [candle.period_start for candle in page.candles]

    assert {start.hour for start in starts} <= {0, 4, 8, 12, 16, 20}
    assert all(start.minute == 0 and start.second == 0 for start in starts)
    # And the same thing said the way the module says it, so this fails if the module's
    # arithmetic ever stops agreeing with the provider.
    assert all(bucket_start(start, Resolution.HOUR_4) == start for start in starts)


@pytest.mark.parametrize("symbol", [CONTINUOUS, SESSION_BOUND])
async def test_a_derived_four_hour_candle_matches_the_provider_s_own(
    gateway: GatewayHistory, db: asyncpg.Connection, symbol: str
) -> None:
    """The claim in full: build `HOUR_4` from minutes and compare it to the observation.

    Only complete periods are compared. A period the minute series covers in part would
    differ for a reason that says nothing about the boundary, which is what is under test.
    """
    minutes = await gateway.history(symbol, Resolution.MINUTE, MINUTES)
    observed = await gateway.history(symbol, Resolution.HOUR_4, FOUR_HOUR_BARS)
    assert minutes.candles, f"the demo API returned no minute candles for {symbol}"

    await write_candles(db, minutes.candles)
    await refresh(
        db,
        symbol,
        Resolution.HOUR_4,
        minutes.candles[0].period_start,
        minutes.candles[-1].period_start,
    )
    derived = {c.period_start: c for c in await read_derived(db, symbol, Resolution.HOUR_4)}

    compared = 0
    for candle in observed.candles:
        ours = derived.get(candle.period_start)
        if ours is None or not ours.complete:
            continue
        compared += 1
        where = f"{symbol} {candle.period_start.isoformat()}"
        assert ours.open == pytest.approx(candle.open, abs=TOLERANCE), f"open at {where}"
        assert ours.high == pytest.approx(candle.high, abs=TOLERANCE), f"high at {where}"
        assert ours.low == pytest.approx(candle.low, abs=TOLERANCE), f"low at {where}"
        assert ours.close == pytest.approx(candle.close, abs=TOLERANCE), f"close at {where}"

    assert compared >= 2, (
        f"only {compared} complete four-hour periods lined up for {symbol}; the sample is "
        "too small to have tested anything"
    )


async def test_a_derived_hour_matches_the_provider_s_own(
    gateway: GatewayHistory, db: asyncpg.Connection
) -> None:
    """`HOUR` alongside it. Its anchor is far less doubtful, which is the point: if the
    four-hour comparison fails while this one passes, the boundary is the suspect rather
    than the aggregation."""
    minutes = await gateway.history(CONTINUOUS, Resolution.MINUTE, 600)
    observed = await gateway.history(CONTINUOUS, Resolution.HOUR, 10)

    await write_candles(db, minutes.candles)
    await refresh(
        db,
        CONTINUOUS,
        Resolution.HOUR,
        minutes.candles[0].period_start,
        minutes.candles[-1].period_start,
    )
    derived = {c.period_start: c for c in await read_derived(db, CONTINUOUS, Resolution.HOUR)}

    compared = 0
    for candle in observed.candles:
        ours = derived.get(candle.period_start)
        if ours is None or not ours.complete:
            continue
        compared += 1
        assert ours.open == pytest.approx(candle.open, abs=TOLERANCE)
        assert ours.high == pytest.approx(candle.high, abs=TOLERANCE)
        assert ours.low == pytest.approx(candle.low, abs=TOLERANCE)
        assert ours.close == pytest.approx(candle.close, abs=TOLERANCE)

    assert compared >= 2


@pytest.mark.parametrize("symbol", [CONTINUOUS, SESSION_BOUND])
async def test_the_minute_series_is_dense_enough_to_derive_from(
    gateway: GatewayHistory, symbol: str
) -> None:
    """Whether `complete` means anything in practice.

    A period is marked complete when it holds every minute it could, and that mark is
    only a signal if a whole period is the ordinary case. Measured over three days in
    August 2026, on both a 24/7 instrument and a session-bound one:

        every interior four-hour period   240/240, except
        the period starting 20:00 UTC     233-235/240, every day, both instruments

    The provider pauses for a few minutes around 21:00 UTC daily. So one period in six
    is legitimately short, for every instrument, forever — which is the reason `complete`
    must never be read as "data is missing". Coverage answers that; this does not.
    """
    page = await gateway.history(symbol, Resolution.MINUTE, MINUTES)
    starts = [candle.period_start for candle in page.candles]
    assert len(starts) == len(set(starts))

    span = (starts[-1] - starts[0]) // timedelta(minutes=1) + 1
    present = len(starts) / span
    assert present > 0.99, (
        f"only {present:.1%} of the minutes across {symbol}'s span came back; the series is "
        "too sparse for a derived candle to mean much"
    )

    whole = sum(1 for count in Counter(bucket_start(s, Resolution.HOUR_4) for s in starts).values()
                if count == 240)
    assert whole >= 1, (
        f"no four-hour period of {symbol} held all 240 of its minutes, so `complete` is a "
        "mark nothing ever earns"
    )
