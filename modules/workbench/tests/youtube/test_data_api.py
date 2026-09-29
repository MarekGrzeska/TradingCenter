"""The Data API source against recorded-shape answers — no network, and no key that means anything."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx

from youtube_data.providers.base import ChannelNotFound, Meter, QuotaExceeded, SourceUnavailable
from youtube_data.providers.data_api import API_URL, DataApiSource, duration_seconds

from .builders import CHANNEL_ID, api_video

KEY = "AIza-not-a-real-key"


@pytest.fixture
def meter() -> Meter:
    return Meter()


@pytest.fixture
async def source(meter):
    async with httpx.AsyncClient() as http:
        yield DataApiSource(http, api_key=KEY, meter=meter)


@pytest.mark.parametrize(
    ("iso", "seconds"),
    [("PT12M30S", 750), ("PT1H", 3600), ("PT1H2M3S", 3723), ("P1DT1H", 90000), ("PT45S", 45), ("P0D", None), (None, None)],
)
def test_a_duration_is_seconds_and_no_length_is_not_zero(iso, seconds) -> None:
    assert duration_seconds(iso) == seconds


@respx.mock
async def test_listing_uploads_is_two_calls_that_cost_two_units(source, meter) -> None:
    respx.get(f"{API_URL}/playlistItems").respond(
        json={"items": [{"contentDetails": {"videoId": "v1"}}, {"contentDetails": {"videoId": "v2"}}]}
    )
    details = respx.get(f"{API_URL}/videos").respond(
        json={"items": [api_video("v1"), api_video("v2", duration="PT30S", snippet={"liveBroadcastContent": "live"})]}
    )

    from youtube_data.providers.base import ChannelInfo

    films = await source.latest_videos(ChannelInfo(channel_id=CHANNEL_ID, title="A Channel"))

    assert [(f.video_id, f.duration_seconds, f.live_status) for f in films] == [
        ("v1", 750, "none"),
        ("v2", 30, "live"),
    ]
    assert dict(details.calls.last.request.url.params)["id"] == "v1,v2"
    assert meter.drain() == {("data_api", "api_units"): 2}


@respx.mock
async def test_a_search_costs_a_hundred_units_and_asks_for_the_newest(source, meter) -> None:
    search = respx.get(f"{API_URL}/search").respond(json={"items": [{"id": {"videoId": "v1"}}]})
    respx.get(f"{API_URL}/videos").respond(json={"items": [api_video("v1")]})

    films = await source.search(
        "gold outlook", language="en", published_after=datetime(2026, 9, 26, 12, 0, tzinfo=UTC), limit=5
    )

    params = dict(search.calls.last.request.url.params)
    assert (params["q"], params["order"], params["publishedAfter"]) == (
        "gold outlook",
        "date",
        "2026-09-26T12:00:00Z",
    )
    assert [f.video_id for f in films] == ["v1"]
    assert meter.drain() == {("data_api", "api_units"): 101}


@respx.mock
async def test_a_handle_is_resolved_and_an_unknown_one_is_named(source) -> None:
    route = respx.get(f"{API_URL}/channels")
    route.respond(
        json={
            "items": [
                {
                    "id": CHANNEL_ID,
                    "snippet": {"title": "Gold Talk", "customUrl": "@goldtalk"},
                    "contentDetails": {"relatedPlaylists": {"uploads": "UU" + CHANNEL_ID[2:]}},
                }
            ]
        }
    )

    info = await source.resolve_channel("@goldtalk")

    assert dict(route.calls.last.request.url.params)["forHandle"] == "@goldtalk"
    assert (info.channel_id, info.title) == (CHANNEL_ID, "Gold Talk")

    route.respond(json={})
    with pytest.raises(ChannelNotFound):
        await source.resolve_channel("@nobody-here")


@respx.mock
async def test_a_spent_quota_is_told_apart_from_a_refusal_and_still_counted(source, meter) -> None:
    respx.get(f"{API_URL}/search").respond(
        status_code=403, json={"error": {"errors": [{"reason": "quotaExceeded"}]}}
    )

    with pytest.raises(QuotaExceeded):
        await source.search("gold", language="", published_after=None, limit=5)
    assert meter.drain() == {("data_api", "api_units"): 100}

    respx.get(f"{API_URL}/videos").respond(
        status_code=403, json={"error": {"errors": [{"reason": "forbidden"}]}}
    )
    with pytest.raises(SourceUnavailable, match="restricted"):
        await source.video_details(["v1"])


@respx.mock
async def test_the_key_is_in_a_header_and_in_no_address(source) -> None:
    """A URL is what an HTTP client logs, and the last credential to reach a log that way was a Telegram bot's. Every
    request this source makes is checked, not one of them."""
    respx.get(f"{API_URL}/channels").respond(json={"items": []})
    respx.get(f"{API_URL}/playlistItems").respond(json={"items": [{"contentDetails": {"videoId": "v1"}}]})
    respx.get(f"{API_URL}/search").respond(json={"items": []})
    respx.get(f"{API_URL}/videos").respond(json={"items": [api_video("v1")]})

    from youtube_data.providers.base import ChannelInfo

    with pytest.raises(ChannelNotFound):
        await source.resolve_channel("@somechannel")
    await source.latest_videos(ChannelInfo(channel_id=CHANNEL_ID, title="A Channel"))
    await source.search("gold", language="en", published_after=None, limit=3)

    sent = [call.request for call in respx.calls]
    assert len(sent) == 4
    for request in sent:
        assert KEY not in str(request.url)
        assert request.headers["x-goog-api-key"] == KEY
