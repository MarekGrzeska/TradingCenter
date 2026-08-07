from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from capital_gateway import history
from capital_gateway.adapter import CapitalAdapter
from capital_gateway.client import CapitalClient
from capital_gateway.config import DEMO_BASE_URL, Settings
from capital_gateway.dtos import Candle, Resolution

API = f"{DEMO_BASE_URL}/api/v1"
STEP = timedelta(minutes=5)


def candles(newest: datetime, count: int) -> list[Candle]:
    """A page, oldest first — the order the provider returns."""
    return [
        Candle(
            ts=f"{(newest - STEP * (count - 1 - i)).strftime('%Y-%m-%dT%H:%M:%S')}Z",
            open=1.0,
            high=1.0,
            low=1.0,
            close=1.0,
            resolution=Resolution.MINUTE_5,
        )
        for i in range(count)
    ]


# --- window arithmetic ---


def test_a_window_is_one_period_short_of_the_count() -> None:
    # Measured: 999 steps pass, 1000 answer error.invalid.max.daterange, because the
    # window counts both edges.
    assert history.window_seconds(Resolution.MINUTE_5, 1000) == 999 * 300


def test_the_provider_format_carries_no_zone_marker() -> None:
    stamp = history.iso_utc(datetime(2026, 7, 23, 14, 19, tzinfo=UTC))
    assert stamp == "2026-07-23T14:19:00"
    assert "Z" not in stamp and "+" not in stamp


def test_a_stored_timestamp_round_trips() -> None:
    assert history.parse_candle_ts("2026-07-23T14:19:00Z") == datetime(
        2026, 7, 23, 14, 19, tzinfo=UTC
    )


# --- the paging loop ---


async def test_a_multi_page_read_returns_one_ordered_series() -> None:
    newest = datetime(2026, 7, 23, 14, 0, tzinfo=UTC)
    pages = [candles(newest, 3), candles(newest - STEP * 3, 3)]
    seen: list[tuple[str | None, str | None]] = []

    async def fetch(date_from, date_to, limit):
        seen.append((date_from, date_to))
        return pages.pop(0) if pages else []

    result = await history.collect("GOLD", Resolution.MINUTE_5, 6, fetch)

    assert result.count == 6
    stamps = [c.ts for c in result.candles]
    assert stamps == sorted(stamps)
    assert len(set(stamps)) == 6
    # The first request names no window — "the newest available" has no anchor yet.
    assert seen[0] == (None, None)
    assert result.first_ts == stamps[0]
    assert result.last_ts == stamps[-1]


async def test_the_next_window_is_anchored_on_the_oldest_candle_received() -> None:
    newest = datetime(2026, 7, 23, 14, 0, tzinfo=UTC)
    # A short page is what a weekend looks like: far fewer candles than the window.
    short_page = candles(newest, 2)
    pages = [short_page, candles(newest - STEP * 50, 2)]
    seen: list[tuple[str | None, str | None]] = []

    async def fetch(date_from, date_to, limit):
        seen.append((date_from, date_to))
        return pages.pop(0) if pages else []

    await history.collect("GOLD", Resolution.MINUTE_5, 4, fetch)

    # The second window ends at the oldest candle actually received, not at
    # "first request minus one window" — which is what leaves a hole across a weekend.
    assert seen[1][1] == history.iso_utc(history.parse_candle_ts(short_page[0].ts))


async def test_running_past_the_bottom_keeps_what_was_collected() -> None:
    calls = 0

    async def fetch(date_from, date_to, limit):
        nonlocal calls
        calls += 1
        if calls == 1:
            return candles(datetime(2026, 7, 23, 14, 0, tzinfo=UTC), 3)
        return None  # error.prices.not-found

    result = await history.collect("GOLD", Resolution.MINUTE_5, 100, fetch)

    # Not an error: an instrument whose history is shorter than the request.
    assert result.count == 3
    assert result.history_ended is True
    assert result.requested == 100


async def test_a_window_with_no_progress_ends_the_loop() -> None:
    page = candles(datetime(2026, 7, 23, 14, 0, tzinfo=UTC), 3)

    async def fetch(date_from, date_to, limit):
        return page  # the same candles, forever

    result = await history.collect("GOLD", Resolution.MINUTE_5, 100, fetch)

    # Without the no-progress check this loops until the request count runs away.
    assert result.requests == 2
    assert result.count == 3
    assert result.history_ended is True


async def test_overlapping_pages_are_deduped() -> None:
    newest = datetime(2026, 7, 23, 14, 0, tzinfo=UTC)
    pages = [candles(newest, 3), candles(newest - STEP * 2, 3)]  # one candle in common

    async def fetch(date_from, date_to, limit):
        return pages.pop(0) if pages else []

    result = await history.collect("GOLD", Resolution.MINUTE_5, 10, fetch)

    stamps = [c.ts for c in result.candles]
    assert len(stamps) == len(set(stamps)) == 5


async def test_a_satisfied_request_does_not_claim_history_ended() -> None:
    async def fetch(date_from, date_to, limit):
        return candles(datetime(2026, 7, 23, 14, 0, tzinfo=UTC), 5)

    result = await history.collect("GOLD", Resolution.MINUTE_5, 5, fetch)

    assert result.count == 5
    assert result.history_ended is False


async def test_paging_stops_when_the_caller_is_gone() -> None:
    calls = 0

    async def fetch(date_from, date_to, limit):
        nonlocal calls
        calls += 1
        return candles(datetime(2026, 7, 23, 14, 0, tzinfo=UTC) - STEP * 3 * calls, 3)

    async def still_wanted() -> bool:
        return calls < 2

    result = await history.collect("GOLD", Resolution.MINUTE_5, 1000, fetch, still_wanted)

    assert calls == 2
    # What was collected is still returned — a client that gave up is not an error.
    assert result.count == 6


# --- through the adapter ---


@pytest.fixture
def adapter() -> CapitalAdapter:
    return CapitalAdapter(
        CapitalClient(
            Settings(
                capital_api_key="k",
                capital_identifier="me@example.com",
                capital_password="p",
                _env_file=None,
            )
        )
    )


@respx.mock
async def test_the_adapter_treats_not_found_as_an_ending(adapter: CapitalAdapter) -> None:
    respx.post(f"{API}/session").mock(
        return_value=httpx.Response(200, headers={"CST": "c", "X-SECURITY-TOKEN": "t"}, json={})
    )
    prices = respx.get(f"{API}/prices/GOLD")
    prices.side_effect = [
        httpx.Response(200, json={"prices": [{"snapshotTimeUTC": "2026-07-23T14:19:00"}]}),
        httpx.Response(404, json={"errorCode": history.HISTORY_EXHAUSTED}),
    ]

    result = await adapter.get_history("GOLD", Resolution.MINUTE_5, 500)

    # A 404 carrying that code is the bottom of history, not an unknown symbol — the
    # distinction decides whether a caller keeps a partial series or gets an exception.
    assert result.count == 1
    assert result.history_ended is True
    await adapter.aclose()
