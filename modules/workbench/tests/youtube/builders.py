"""Data as builders, so a test names only what it is about."""

from __future__ import annotations

CHANNEL_ID = "UC" + "a" * 22
OTHER_CHANNEL_ID = "UC" + "b" * 22
VIDEO_ID = "dQw4w9WgXcQ"


def feed(channel_id: str = CHANNEL_ID, *, title: str = "A Channel", entries: list[dict] | None = None) -> str:
    """A channel's Atom feed as YouTube publishes it, with the elements this package reads and the ones it ignores."""
    rows = "".join(
        f"""
  <entry>
    <id>yt:video:{entry['video_id']}</id>
    <yt:videoId>{entry['video_id']}</yt:videoId>
    <yt:channelId>{channel_id[2:] if entry.get('bare_channel') else channel_id}</yt:channelId>
    <title>{entry.get('title', 'A film')}</title>
    <published>{entry.get('published', '2026-09-27T10:00:00+00:00')}</published>
    <media:group><media:title>ignored</media:title></media:group>
  </entry>"""
        for entry in (entries or [])
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" '
        'xmlns:media="http://search.yahoo.com/mrss/" xmlns="http://www.w3.org/2005/Atom">'
        f"<title>{title}</title>{rows}</feed>"
    )


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
