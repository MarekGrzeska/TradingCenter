"""The seam between the two roads a candle travels (3.4).

`capital-gateway` spells a period start twice over — an ISO string over REST, epoch
seconds over the WebSocket — and calls the split deliberate. For a chart it costs
nothing. For an archive keyed on `(symbol, resolution, period_start)` a one-second or
one-timezone disagreement is not a rounding difference: it is a second row where there
should have been an overwrite, and a duplicate candle in every series read afterwards.

So the claim is checked where it matters, through both clients rather than through the
parser they share.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest
import respx

from market_data.gateway import CandleUpdate, GatewayHistory, read_message
from market_data.models import CandleSource, Resolution

BASE_URL = "http://gateway.test:8010"

# 2026-08-07 12:00:00 UTC, written twice. The constant is spelled out rather than
# computed from the datetime beside it, so a bug in the conversion cannot agree with
# itself and pass.
PERIOD_START = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
PERIOD_START_ISO = "2026-08-07T12:00:00Z"
PERIOD_START_EPOCH = 1_786_104_000


async def a_history_candle(ts: str):
    payload = {
        "candles": [
            {
                "ts": ts,
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 1000.0,
                "resolution": "MINUTE_5",
            }
        ],
        "count": 1,
        "requested": 1000,
        "requests": 1,
        "resolution": "MINUTE_5",
        "first_ts": ts,
        "last_ts": ts,
        "history_ended": False,
    }
    with respx.mock:
        respx.get(f"{BASE_URL}/instruments/US100/history").mock(
            return_value=httpx.Response(200, json=payload)
        )
        async with httpx.AsyncClient() as client:
            page = await GatewayHistory(BASE_URL, client).history(
                "US100", Resolution.MINUTE_5, 1000
            )
    return page.candles[0]


def a_stream_candle(time: int):
    message = read_message(
        json.dumps(
            {
                "kind": "candle",
                "symbol": "US100",
                "resolution": "MINUTE_5",
                "time": time,
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": None,
                "forming": False,
            }
        )
    )
    assert isinstance(message, CandleUpdate)
    return message.candle


async def test_the_same_period_from_both_roads_carries_the_same_timestamp() -> None:
    from_history = await a_history_candle(PERIOD_START_ISO)
    from_stream = a_stream_candle(PERIOD_START_EPOCH)

    assert from_history.period_start == from_stream.period_start == PERIOD_START


async def test_the_two_candles_key_the_same_archive_row() -> None:
    # The identity the store is keyed on, compared whole — a matching timestamp is not
    # enough if the symbol or the resolution crossed differently.
    from_history = await a_history_candle(PERIOD_START_ISO)
    from_stream = a_stream_candle(PERIOD_START_EPOCH)

    def key(candle):
        return (candle.symbol, candle.resolution, candle.period_start)

    assert key(from_history) == key(from_stream)


async def test_only_the_provenance_differs() -> None:
    # Everything a later authority rule needs to prefer one over the other, and nothing
    # it would have to guess at.
    from_history = await a_history_candle(PERIOD_START_ISO)
    from_stream = a_stream_candle(PERIOD_START_EPOCH)

    assert from_history.source is CandleSource.HISTORY
    assert from_stream.source is CandleSource.STREAM
    assert from_history.price_side is from_stream.price_side
    assert from_history.forming is from_stream.forming is False


@pytest.mark.parametrize(
    "ts",
    [
        PERIOD_START_ISO,
        "2026-08-07T12:00:00",  # no zone marker, the broker-local fallback
        "2026-08-07T14:00:00+02:00",  # an offset, the same instant
    ],
)
async def test_every_form_the_history_side_can_send_meets_the_stream(ts: str) -> None:
    # The gateway's REST candle carries whichever of these the provider gave it. All
    # three are the same period, and all three have to key the same row as the stream's.
    from_history = await a_history_candle(ts)

    assert from_history.period_start == a_stream_candle(PERIOD_START_EPOCH).period_start
