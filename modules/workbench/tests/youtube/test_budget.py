"""The followed channels' share of the source's day, which topics may not search into."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from youtube_data.budget import channels_reserve


@pytest.mark.parametrize(
    ("at", "channels", "reserve"),
    [
        (datetime(2026, 10, 25, 0, 0, tzinfo=UTC), 1, 2 * 48),
        (datetime(2026, 10, 25, 23, 10, tzinfo=UTC), 1, 2 * 2),  # a pass part-way to midnight is still a pass
        (datetime(2026, 10, 25, 12, 0, tzinfo=UTC), 3, 3 * 2 * 24),
        (datetime(2026, 10, 25, 12, 0, tzinfo=UTC), 0, 0),
    ],
)
def test_the_channels_keep_one_listing_each_for_every_pass_left_in_the_utc_day(at, channels, reserve) -> None:
    assert channels_reserve(channels, 2, now=at, interval_seconds=1800) == reserve
