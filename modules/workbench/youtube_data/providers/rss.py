"""Films from a channel's public feed: no key, no quota, and no idea how long any of them is. It lists the fifteen most
recent uploads and cannot search, so it is the source for working with nothing configured — and the reason a source
that *can* search and measure exists beside it."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import httpx
from defusedxml import DefusedXmlException, ElementTree

from .base import (
    ChannelInfo,
    ChannelNotFound,
    Meter,
    SourceUnavailable,
    UnsupportedOperation,
    UnsupportedReference,
    VideoRef,
)
from .refs import channel_ref, uploads_playlist

FEED_URL = "https://www.youtube.com/feeds/videos.xml"

_NS = {
    "a": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
}


class RssSource:
    name = "rss"
    unit = "requests"
    search_cost = 0
    supports_search = False
    supports_handles = False

    def __init__(self, http: httpx.AsyncClient, *, meter: Meter) -> None:
        self._http = http
        self._meter = meter

    async def _feed(self, channel_id: str):
        try:
            response = await self._http.get(FEED_URL, params={"channel_id": channel_id})
        except httpx.HTTPError as err:
            raise SourceUnavailable(f"the feed for {channel_id} did not answer: {err}") from err
        self._meter.record(self.name, "requests", 1)
        if response.status_code == 404:
            raise ChannelNotFound(f"YouTube has no channel {channel_id}")
        if response.is_error:
            raise SourceUnavailable(f"the feed for {channel_id} answered {response.status_code}")
        try:
            return ElementTree.fromstring(response.content)
        except (ElementTree.ParseError, DefusedXmlException) as err:
            raise SourceUnavailable(f"the feed for {channel_id} is not a document: {err}") from err

    async def resolve_channel(self, reference: str) -> ChannelInfo:
        ref = channel_ref(reference)
        if ref.kind != "id":
            raise UnsupportedReference(
                f"{reference!r} is an @handle, which the feed source cannot resolve: give the channel's "
                "youtube.com/channel/UC… address, or set YOUTUBE_VIDEO_SOURCE=data_api"
            )
        root = await self._feed(ref.value)
        title = (root.findtext("a:title", default="", namespaces=_NS) or "").strip()
        return ChannelInfo(
            channel_id=ref.value, title=title or ref.value, uploads_playlist_id=uploads_playlist(ref.value)
        )

    async def latest_videos(self, channel: ChannelInfo) -> list[VideoRef]:
        root = await self._feed(channel.channel_id)
        channel_title = (root.findtext("a:title", default="", namespaces=_NS) or channel.title).strip()
        videos: list[VideoRef] = []
        for entry in root.findall("a:entry", _NS):
            video_id = entry.findtext("yt:videoId", namespaces=_NS)
            published = entry.findtext("a:published", namespaces=_NS)
            if not video_id or not published:
                continue
            try:
                published_at = datetime.fromisoformat(published)
            except ValueError:
                continue
            videos.append(
                VideoRef(
                    video_id=video_id,
                    channel_id=entry.findtext("yt:channelId", namespaces=_NS) or channel.channel_id,
                    channel_title=channel_title,
                    title=(entry.findtext("a:title", default="", namespaces=_NS) or "").strip(),
                    published_at=published_at,
                )
            )
        return videos

    async def search(
        self, phrase: str, *, language: str, published_after: datetime | None, limit: int
    ) -> list[VideoRef]:
        raise UnsupportedOperation(
            "the feed source cannot search: set YOUTUBE_VIDEO_SOURCE=data_api (a free YouTube Data API key)"
        )

    async def video_details(self, video_ids: Sequence[str]) -> list[VideoRef]:
        raise UnsupportedOperation(
            "the feed source knows nothing of a film it was not asked to follow: set YOUTUBE_VIDEO_SOURCE=data_api"
        )
