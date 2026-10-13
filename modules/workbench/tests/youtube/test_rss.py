"""The feed source against documents as YouTube publishes them — no network."""

from __future__ import annotations

import httpx
import pytest
import respx

from youtube_data.providers.base import (
    ChannelInfo,
    ChannelNotFound,
    Meter,
    SourceUnavailable,
    UnsupportedOperation,
    UnsupportedReference,
)
from youtube_data.providers.rss import FEED_URL, RssSource

from .builders import CHANNEL_ID, feed


@pytest.fixture
def meter() -> Meter:
    return Meter()


@pytest.fixture
async def source(meter):
    async with httpx.AsyncClient() as http:
        yield RssSource(http, meter=meter)


@respx.mock
async def test_a_feed_becomes_films_with_no_length_because_a_feed_has_none(source, meter) -> None:
    respx.get(FEED_URL, params={"channel_id": CHANNEL_ID}).respond(
        text=feed(entries=[{"video_id": "v1", "title": "First"}, {"video_id": "v2"}])
    )

    films = await source.latest_videos(ChannelInfo(channel_id=CHANNEL_ID, title="A Channel"))

    assert [film.video_id for film in films] == ["v1", "v2"]
    assert films[0].title == "First"
    assert films[0].channel_title == "A Channel"
    assert films[0].duration_seconds is None
    assert meter.drain() == {("rss", "requests"): 1}


@respx.mock
async def test_resolving_a_channel_reads_its_title_from_the_feed(source) -> None:
    respx.get(FEED_URL).respond(text=feed(title="Gold Talk"))

    info = await source.resolve_channel(f"https://www.youtube.com/channel/{CHANNEL_ID}")

    assert (info.channel_id, info.title) == (CHANNEL_ID, "Gold Talk")
    assert info.uploads_playlist_id == "UU" + CHANNEL_ID[2:]


@respx.mock
async def test_a_channel_that_does_not_exist_is_named_as_such(source) -> None:
    respx.get(FEED_URL).respond(status_code=404)

    with pytest.raises(ChannelNotFound):
        await source.resolve_channel(CHANNEL_ID)


@respx.mock
@pytest.mark.parametrize("failure", [httpx.Response(503), httpx.Response(200, text="<not-xml")])
async def test_a_feed_that_will_not_answer_leaves_the_archive_alone(source, failure) -> None:
    respx.get(FEED_URL).mock(return_value=failure)

    with pytest.raises(SourceUnavailable):
        await source.latest_videos(ChannelInfo(channel_id=CHANNEL_ID, title="A Channel"))


async def test_what_a_feed_cannot_do_says_what_would(source) -> None:
    with pytest.raises(UnsupportedReference, match="data_api"):
        await source.resolve_channel("@somechannel")
    with pytest.raises(UnsupportedOperation, match="data_api"):
        await source.search("gold", language="en", published_after=None, limit=5)
    with pytest.raises(UnsupportedOperation, match="data_api"):
        await source.video_details(["v1"])
