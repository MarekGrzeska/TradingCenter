"""Test data, built rather than written out: a test names the one field it is about and inherits the rest."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from social_data.models import RawPost

TRUTH_SOCIAL = "truth_social"

# A fixed moment, so a test that sorts by time reads the same on every run.
NOON = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


def raw_post(
    external_id: str = "1",
    *,
    source: str = TRUTH_SOCIAL,
    author: str = "realDonaldTrump",
    content: str = "TARIFFS ARE COMING.",
    published_at: datetime | None = None,
    minutes_ago: float | None = None,
    url: str | None = "https://trumpstruth.org/statuses/1",
    is_repost: bool = False,
) -> RawPost:
    """One post as a source hands it over. `minutes_ago` is relative to now, for a window test that
    has to be about the real clock; `published_at` is absolute, for one that must not be."""
    if published_at is None:
        published_at = (
            NOON if minutes_ago is None else datetime.now(UTC) - timedelta(minutes=minutes_ago)
        )
    return RawPost(
        source=source,
        external_id=external_id,
        author=author,
        content=content,
        published_at=published_at,
        url=url,
        is_repost=is_repost,
    )
