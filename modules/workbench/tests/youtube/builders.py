"""Data as builders, so a test names only what it is about."""

from __future__ import annotations

CHANNEL_ID = "UC" + "a" * 22
OTHER_CHANNEL_ID = "UC" + "b" * 22
VIDEO_ID = "dQw4w9WgXcQ"


def api_video(video_id: str = VIDEO_ID, **overrides) -> dict:
    """One `videos.list` item."""
    snippet = {
        "publishedAt": "2026-09-27T10:00:00Z",
        "channelId": CHANNEL_ID,
        "channelTitle": "A Channel",
        "title": "A film",
        "liveBroadcastContent": "none",
    }
    snippet.update(overrides.pop("snippet", {}))
    return {
        "id": video_id,
        "snippet": snippet,
        "contentDetails": {"duration": overrides.pop("duration", "PT12M30S")},
    }
