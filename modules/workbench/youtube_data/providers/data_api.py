"""Films from the YouTube Data API v3 — the one real source: a free key, ten thousand units a day, and every answer the
loop needs before it pays for a transcript — how long a film is, whether it is live, what language it speaks, a channel
by its `@handle`, a search. Listing a channel's uploads is one unit; a search is a hundred, which is why topics carry
their own limits and the day has a ceiling (`youtube-data-transcripts`).

The key travels in a header. The API also accepts `?key=`, and that is the spelling this module never uses: a URL is
what an HTTP client logs, and the last credential that reached a log that way was a Telegram bot's."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import UTC, datetime

import httpx

from .base import (
    ChannelInfo,
    ChannelNotFound,
    Meter,
    QuotaExceeded,
    SourceUnavailable,
    VideoRef,
)
from .refs import channel_ref, uploads_playlist

API_URL = "https://www.googleapis.com/youtube/v3"

# What each call costs, from Google's own quota table. Recorded per call, so the day's ceiling is arithmetic.
COST_LIST = 1
COST_SEARCH = 100

# The API answers at most fifty per page for every list this module reads.
PAGE = 50

_DURATION = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")


def duration_seconds(iso: str | None) -> int | None:
    """`PT1H2M3S` as seconds. `P0D` — what an upcoming premiere carries — is `None`: no length is not a zero-length film."""
    if not iso:
        return None
    match = _DURATION.match(iso)
    if match is None:
        return None
    days, hours, minutes, seconds = (int(part or 0) for part in match.groups())
    total = ((days * 24 + hours) * 60 + minutes) * 60 + seconds
    return total or None


class DataApiSource:
    name = "data_api"
    unit = "api_units"
    # The search itself and the details call that follows it, which is always made.
    search_cost = COST_SEARCH + COST_LIST

    def __init__(self, http: httpx.AsyncClient, *, api_key: str, meter: Meter) -> None:
        self._http = http
        self._key = api_key
        self._meter = meter

    async def _get(self, resource: str, params: dict[str, str | int], cost: int) -> dict:
        try:
            response = await self._http.get(
                f"{API_URL}/{resource}", params=params, headers={"X-goog-api-key": self._key}
            )
        except httpx.HTTPError as err:
            raise SourceUnavailable(f"the YouTube Data API did not answer {resource}: {err}") from err
        # A refused call is still a call as far as the quota is concerned, so it is counted before it is judged.
        self._meter.record(self.name, "api_units", cost)
        if response.status_code in (403, 429):
            reasons = _error_reasons(response)
            if "quotaExceeded" in reasons or "dailyLimitExceeded" in reasons or response.status_code == 429:
                raise QuotaExceeded("the YouTube Data API's daily quota is spent")
            raise SourceUnavailable(
                f"the YouTube Data API refused {resource} ({','.join(reasons) or response.status_code}) — "
                "is the key restricted to another API?"
            )
        if response.is_error:
            raise SourceUnavailable(f"the YouTube Data API answered {response.status_code} for {resource}")
        # A proxy's or a captive portal's page arrives as a 200 too.
        try:
            body = response.json()
        except ValueError as err:
            raise SourceUnavailable(f"the YouTube Data API's answer to {resource} is not JSON") from err
        if not isinstance(body, dict):
            raise SourceUnavailable(f"the YouTube Data API's answer to {resource} is not an object")
        return body

    async def resolve_channel(self, reference: str) -> ChannelInfo:
        ref = channel_ref(reference)
        params: dict[str, str | int] = {"part": "snippet,contentDetails"}
        params["forHandle" if ref.kind == "handle" else "id"] = ref.value
        body = await self._get("channels", params, COST_LIST)
        items = body.get("items") or []
        if not items:
            raise ChannelNotFound(f"YouTube has no channel {reference!r}")
        item = items[0]
        channel_id = item["id"]
        snippet = item.get("snippet", {})
        return ChannelInfo(
            channel_id=channel_id,
            title=snippet.get("title", channel_id),
            handle=snippet.get("customUrl"),
            uploads_playlist_id=(item.get("contentDetails", {}).get("relatedPlaylists", {}) or {}).get(
                "uploads"
            )
            or uploads_playlist(channel_id),
        )

    async def latest_videos(self, channel: ChannelInfo) -> list[VideoRef]:
        playlist = channel.uploads_playlist_id or uploads_playlist(channel.channel_id)
        body = await self._get(
            "playlistItems",
            {"part": "contentDetails", "playlistId": playlist, "maxResults": 15},
            COST_LIST,
        )
        ids = [
            item["contentDetails"]["videoId"]
            for item in body.get("items", [])
            if item.get("contentDetails", {}).get("videoId")
        ]
        return await self.video_details(ids)

    async def search(
        self, phrase: str, *, language: str, published_after: datetime | None, limit: int
    ) -> list[VideoRef]:
        params: dict[str, str | int] = {
            "part": "snippet",
            "type": "video",
            "q": phrase,
            "order": "date",
            "maxResults": min(max(limit, 1), PAGE),
        }
        if language:
            params["relevanceLanguage"] = language
        if published_after is not None:
            params["publishedAfter"] = published_after.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        body = await self._get("search", params, COST_SEARCH)
        ids = [
            item["id"]["videoId"] for item in body.get("items", []) if item.get("id", {}).get("videoId")
        ]
        return await self.video_details(ids)

    async def video_details(self, video_ids: Sequence[str]) -> list[VideoRef]:
        """Length, live state and channel for up to fifty films in one unit — which is why a listing is never enough
        on its own: it names films and says nothing that would let the loop skip one."""
        films: list[VideoRef] = []
        for start in range(0, len(video_ids), PAGE):
            chunk = video_ids[start : start + PAGE]
            body = await self._get(
                "videos", {"part": "snippet,contentDetails", "id": ",".join(chunk)}, COST_LIST
            )
            for item in body.get("items", []):
                snippet = item.get("snippet", {})
                published = snippet.get("publishedAt")
                if not published:
                    continue
                films.append(
                    VideoRef(
                        video_id=item["id"],
                        channel_id=snippet.get("channelId"),
                        channel_title=snippet.get("channelTitle", ""),
                        title=snippet.get("title", ""),
                        published_at=datetime.fromisoformat(published),
                        duration_seconds=duration_seconds(item.get("contentDetails", {}).get("duration")),
                        live_status=_live_status(snippet.get("liveBroadcastContent")),
                        audio_language=audio_language(snippet.get("defaultAudioLanguage")),
                    )
                )
        return films


def audio_language(value: str | None) -> str | None:
    """`en-US` as `en`: automatic captions carry the bare language, and asking for the regional one would miss them."""
    if not value or not value.strip():
        return None
    return value.strip().split("-")[0].lower()


def _live_status(value: str | None) -> str:
    return value if value in {"none", "live", "upcoming"} else "none"


def _error_reasons(response: httpx.Response) -> list[str]:
    try:
        errors = response.json().get("error", {}).get("errors", [])
    except ValueError:
        return []
    return [str(error.get("reason", "")) for error in errors if isinstance(error, dict)]
