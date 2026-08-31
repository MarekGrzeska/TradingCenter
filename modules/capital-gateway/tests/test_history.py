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


async def test_an_empty_first_window_is_not_the_end_of_history() -> None:
    """`not-found` before a single candle has been collected says nothing about the bottom of the
    instrument. Read as an ending it cost US100 its whole history below January 2026."""

    async def fetch(date_from, date_to, limit):
        return None  # error.prices.not-found, on the very first window

    result = await history.collect("GOLD", Resolution.MINUTE_5, 100, fetch)

    assert result.count == 0
    assert result.history_ended is False
    assert result.requests == 1


async def test_an_empty_first_window_with_an_anchor_is_not_an_ending_either() -> None:
    """The same read as above with a past anchor — the shape a job chunk uses, and the
    one that produced the failure in production."""

    async def fetch(date_from, date_to, limit):
        return None

    result = await history.collect(
        "GOLD",
        Resolution.MINUTE_5,
        100,
        fetch,
        anchor=datetime(2026, 1, 1, tzinfo=UTC),
        after=datetime(2024, 1, 1, tzinfo=UTC),
    )

    assert result.count == 0
    assert result.history_ended is False


async def test_an_empty_window_after_a_full_one_still_ends_history() -> None:
    """The behaviour the change must not weaken: once a page has anchored the read, a
    window running out is the provider's own bottom."""
    calls = 0

    async def fetch(date_from, date_to, limit):
        nonlocal calls
        calls += 1
        if calls == 1:
            return candles(datetime(2026, 7, 23, 14, 0, tzinfo=UTC), 3)
        return None

    result = await history.collect("GOLD", Resolution.MINUTE_5, 100, fetch)

    assert result.count == 3
    assert result.history_ended is True


async def test_an_anchor_shapes_only_the_first_page() -> None:
    anchor = datetime(2024, 1, 15, 0, 0, tzinfo=UTC)
    first_page = candles(anchor, 2)
    pages = [first_page, candles(anchor - STEP * 50, 2)]
    seen: list[tuple[str | None, str | None]] = []

    async def fetch(date_from, date_to, limit):
        seen.append((date_from, date_to))
        return pages.pop(0) if pages else []

    await history.collect("GOLD", Resolution.MINUTE_5, 4, fetch, anchor=anchor)

    # The first request now names a window ending at the anchor, not "the newest
    # available" — this is what lets a caller reach for a window that ended in the past.
    assert seen[0] == history.window_before(anchor, Resolution.MINUTE_5, 4)
    # The second page still anchors on data actually received, exactly as an unanchored
    # read would — the anchor only ever shapes the first request.
    oldest_of_first_page = history.parse_candle_ts(first_page[0].ts)
    assert seen[1][1] == history.iso_utc(oldest_of_first_page)


async def test_no_anchor_keeps_reaching_back_from_now() -> None:
    seen: list[tuple[str | None, str | None]] = []

    async def fetch(date_from, date_to, limit):
        seen.append((date_from, date_to))
        return candles(datetime(2026, 7, 23, 14, 0, tzinfo=UTC), 3)

    await history.collect("GOLD", Resolution.MINUTE_5, 3, fetch)

    assert seen[0] == (None, None)


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



async def test_a_floor_drops_candles_older_than_it() -> None:
    # `bars` counts candles, so an instrument shut half the week hands back candles reaching
    # much further into the past than the caller wanted. Nothing older than the floor may come out.
    newest = datetime(2026, 7, 23, 14, 0, tzinfo=UTC)
    floor = newest - STEP * 2
    page = candles(newest, 6)  # reaches back well past the floor

    async def fetch(date_from, date_to, limit):
        return page

    result = await history.collect("GOLD", Resolution.MINUTE_5, 6, fetch, after=floor)

    assert [history.parse_candle_ts(c.ts) for c in result.candles] == [
        floor,
        floor + STEP,
        newest,
    ]


async def test_a_window_never_reaches_past_the_floor() -> None:
    # Clamped rather than merely filtered afterwards, so a request is never spent on
    # candles that would be discarded on arrival.
    anchor = datetime(2026, 7, 23, 14, 0, tzinfo=UTC)
    floor = anchor - STEP * 3
    seen: list[tuple[str | None, str | None]] = []

    async def fetch(date_from, date_to, limit):
        seen.append((date_from, date_to))
        return candles(anchor, 4)

    await history.collect("GOLD", Resolution.MINUTE_5, 1000, fetch, anchor=anchor, after=floor)

    # Without the clamp this window would reach back 999 periods, not three.
    assert seen[0] == (history.iso_utc(floor), history.iso_utc(anchor))


# Four ways a floored read can look like it ran out, none of them the provider's bottom.
# `history_ended` is stored as a permanent boundary, so claiming it stops the next, deeper read.
ANCHOR = datetime(2026, 7, 23, 14, 0, tzinfo=UTC)


def _always(page):
    async def fetch(date_from, date_to, limit):
        return page

    return fetch


def _then_not_found(page):
    pages = [page]

    async def fetch(date_from, date_to, limit):
        return pages.pop(0) if pages else None

    return fetch


@pytest.mark.parametrize(
    ("floor_back", "fetch", "expected_count", "expected_requests"),
    [
        pytest.param(STEP * 3, _always(candles(ANCHOR, 4)), 4, 1, id="window-clamped-to-the-floor"),
        pytest.param(STEP * 3, _always([]), 0, 1, id="empty-window-at-the-floor"),
        pytest.param(
            STEP * 4, _then_not_found(candles(ANCHOR, 2)), 2, 2, id="not-found-for-a-clamped-window"
        ),
        pytest.param(
            STEP * 3 + timedelta(minutes=3),
            _always(candles(ANCHOR, 4)),
            4,
            2,  # the second request is the sliver
            id="no-progress-at-a-clamped-window",
        ),
    ],
)
async def test_a_floored_read_never_claims_the_provider_ran_out(
    floor_back, fetch, expected_count, expected_requests
) -> None:
    result = await history.collect(
        "GOLD", Resolution.MINUTE_5, 1000, fetch, anchor=ANCHOR, after=ANCHOR - floor_back
    )

    assert result.history_ended is False
    assert result.count == expected_count
    assert result.requests == expected_requests


async def test_running_out_of_provider_data_above_the_floor_still_ends_history() -> None:
    # The floor must not mask a genuine ending: it is far enough back that no window is clamped
    # to it, so running out is unambiguously the provider's bottom rather than the caller's bound.
    anchor = datetime(2026, 7, 23, 14, 0, tzinfo=UTC)
    floor = anchor - STEP * 100_000
    pages = [candles(anchor, 3)]

    async def fetch(date_from, date_to, limit):
        return pages.pop(0) if pages else None  # not-found: the bottom of history

    result = await history.collect(
        "GOLD", Resolution.MINUTE_5, 1000, fetch, anchor=anchor, after=floor
    )

    assert result.history_ended is True


async def test_no_floor_leaves_the_read_exactly_as_it_was() -> None:
    anchor = datetime(2026, 7, 23, 14, 0, tzinfo=UTC)
    seen: list[tuple[str | None, str | None]] = []

    async def fetch(date_from, date_to, limit):
        seen.append((date_from, date_to))
        return candles(anchor, 4)

    await history.collect("GOLD", Resolution.MINUTE_5, 4, fetch, anchor=anchor)

    assert seen[0] == history.window_before(anchor, Resolution.MINUTE_5, 4)


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



@pytest.fixture
def adapter() -> CapitalAdapter:
    return CapitalAdapter(
        CapitalClient(
            Settings(
                capital_api_key="k",
                capital_identifier="me@example.com",
                capital_password="p",
                gateway_api_key="g",
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



async def _open() -> bool:
    return True


async def _shut() -> bool:
    return False


async def test_the_newest_candle_of_a_read_reaching_now_is_forming() -> None:
    """MINUTE_5, where the boundary is arithmetic, so the answer is exact and the market
    is never consulted."""
    now = datetime(2026, 7, 23, 14, 3, tzinfo=UTC)
    page = candles(datetime(2026, 7, 23, 14, 0, tzinfo=UTC), 3)

    marked = await history.mark_forming(page, Resolution.MINUTE_5, now, _shut)

    assert [c.forming for c in marked] == [False, False, True]


async def test_a_period_that_has_ended_is_not_forming() -> None:
    now = datetime(2026, 7, 23, 14, 7, tzinfo=UTC)
    page = candles(datetime(2026, 7, 23, 14, 0, tzinfo=UTC), 3)

    marked = await history.mark_forming(page, Resolution.MINUTE_5, now, _open)

    assert [c.forming for c in marked] == [False, False, False]


async def test_a_daily_candle_is_forming_while_the_market_is_open() -> None:
    now = datetime(2026, 7, 23, 14, 0, tzinfo=UTC)
    page = [
        Candle(ts="2026-07-22T00:00:00Z", resolution=Resolution.DAY),
        Candle(ts="2026-07-23T00:00:00Z", resolution=Resolution.DAY),
    ]

    marked = await history.mark_forming(page, Resolution.DAY, now, _open)

    assert [c.forming for c in marked] == [False, True]


async def test_a_daily_candle_is_settled_once_the_market_shuts() -> None:
    """The venue is the only thing that knows where a daily period ends, so a shut market
    is what closes the candle — never arithmetic on UTC midnight."""
    now = datetime(2026, 7, 23, 14, 0, tzinfo=UTC)
    page = [Candle(ts="2026-07-23T00:00:00Z", resolution=Resolution.DAY)]

    marked = await history.mark_forming(page, Resolution.DAY, now, _shut)

    assert marked[0].forming is False


async def test_a_read_anchored_in_the_past_has_nothing_forming() -> None:
    """Every candle of a deep chunk closed long ago, whatever the market is doing now —
    and the market is never asked, so the request is not spent."""
    now = datetime(2026, 7, 23, 14, 0, tzinfo=UTC)
    page = [Candle(ts="2024-03-01T00:00:00Z", resolution=Resolution.DAY)]
    asked = False

    async def market_open() -> bool:
        nonlocal asked
        asked = True
        return True

    marked = await history.mark_forming(page, Resolution.DAY, now, market_open)

    assert marked[0].forming is False
    assert asked is False


async def test_a_fixed_period_read_never_asks_about_the_market() -> None:
    now = datetime(2026, 7, 23, 14, 3, tzinfo=UTC)
    page = candles(datetime(2026, 7, 23, 14, 0, tzinfo=UTC), 2)
    asked = False

    async def market_open() -> bool:
        nonlocal asked
        asked = True
        return True

    marked = await history.mark_forming(page, Resolution.MINUTE_5, now, market_open)

    assert marked[-1].forming is True
    assert asked is False


async def test_marking_leaves_the_page_it_was_given_alone() -> None:
    now = datetime(2026, 7, 23, 14, 3, tzinfo=UTC)
    page = candles(datetime(2026, 7, 23, 14, 0, tzinfo=UTC), 2)

    await history.mark_forming(page, Resolution.MINUTE_5, now, _open)

    assert all(c.forming is False for c in page)


async def test_an_empty_page_marks_nothing() -> None:
    assert await history.mark_forming([], Resolution.DAY, datetime.now(UTC), _open) == []


@respx.mock
async def test_the_adapter_asks_the_market_before_calling_a_daily_candle_settled(
    adapter: CapitalAdapter,
) -> None:
    """End to end for the one resolution that cannot be decided by arithmetic."""
    today = datetime.now(UTC).strftime("%Y-%m-%dT00:00:00")
    respx.post(f"{API}/session").mock(
        return_value=httpx.Response(200, headers={"CST": "c", "X-SECURITY-TOKEN": "t"}, json={})
    )
    respx.get(f"{API}/prices/GOLD").mock(
        return_value=httpx.Response(200, json={"prices": [{"snapshotTimeUTC": today}]})
    )
    market = respx.get(f"{API}/markets/GOLD").mock(
        return_value=httpx.Response(200, json={"snapshot": {"marketStatus": "TRADEABLE"}})
    )

    result = await adapter.get_candles("GOLD", Resolution.DAY, 1)

    assert result[-1].forming is True
    assert market.called
    await adapter.aclose()


@respx.mock
async def test_a_shut_market_settles_todays_daily_candle(adapter: CapitalAdapter) -> None:
    today = datetime.now(UTC).strftime("%Y-%m-%dT00:00:00")
    respx.post(f"{API}/session").mock(
        return_value=httpx.Response(200, headers={"CST": "c", "X-SECURITY-TOKEN": "t"}, json={})
    )
    respx.get(f"{API}/prices/GOLD").mock(
        return_value=httpx.Response(200, json={"prices": [{"snapshotTimeUTC": today}]})
    )
    respx.get(f"{API}/markets/GOLD").mock(
        return_value=httpx.Response(200, json={"snapshot": {"marketStatus": "CLOSED"}})
    )

    result = await adapter.get_candles("GOLD", Resolution.DAY, 1)

    assert result[-1].forming is False
    await adapter.aclose()
