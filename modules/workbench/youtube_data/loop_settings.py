"""The three numbers the operator turns from the terminal: how often the loop passes, and what a topic added without limits of
its own gets. They live in one row; with no row the process settings stand, so a workbench nobody has touched behaves as its
environment says."""

from __future__ import annotations

import math

from . import store
from .config import Settings
from .models import LoopSettings

MIN_POLL_MINUTES = 5
MAX_POLL_MINUTES = 24 * 60
MIN_INTERVAL_MINUTES = 15
MAX_INTERVAL_MINUTES = 7 * 24 * 60
# A topic that may send forty results to be screened every pass is a bill, not a topic.
MAX_VIDEOS_PER_RUN = 20


class SettingsRefused(ValueError):
    """The value is outside what the loop can afford; the message is for the operator."""


def from_process(settings: Settings) -> LoopSettings:
    # Rounded up, never to zero: a test's one-second loop is still a loop that passes.
    return LoopSettings(
        poll_interval_minutes=max(1, math.ceil(settings.poll_interval_seconds / 60)),
        topic_interval_minutes=settings.topic_default_interval_minutes,
        topic_max_videos=settings.topic_default_max_videos,
    )


async def current(conn, settings: Settings) -> LoopSettings:
    return await store.get_loop_settings(conn) or from_process(settings)


def _check(value: LoopSettings) -> None:
    if not MIN_POLL_MINUTES <= value.poll_interval_minutes <= MAX_POLL_MINUTES:
        raise SettingsRefused(
            f"the loop passes every {MIN_POLL_MINUTES} to {MAX_POLL_MINUTES} minutes — every channel costs "
            "source units each pass, and a shorter interval would spend the day's budget before noon"
        )
    if not MIN_INTERVAL_MINUTES <= value.topic_interval_minutes <= MAX_INTERVAL_MINUTES:
        raise SettingsRefused(
            f"a topic is searched every {MIN_INTERVAL_MINUTES} to {MAX_INTERVAL_MINUTES} minutes (a week)"
        )
    if not 1 <= value.topic_max_videos <= MAX_VIDEOS_PER_RUN:
        raise SettingsRefused(f"a topic offers between 1 and {MAX_VIDEOS_PER_RUN} films per search")


async def update(
    pool,
    settings: Settings,
    *,
    poll_interval_minutes: int | None = None,
    topic_interval_minutes: int | None = None,
    topic_max_videos: int | None = None,
) -> LoopSettings:
    """What is given replaces what stands; the rest stays as it was — in force, so the first save writes all three."""
    async with pool.acquire() as conn:
        standing = await current(conn, settings)
        changed = LoopSettings(
            poll_interval_minutes=standing.poll_interval_minutes
            if poll_interval_minutes is None
            else poll_interval_minutes,
            topic_interval_minutes=standing.topic_interval_minutes
            if topic_interval_minutes is None
            else topic_interval_minutes,
            topic_max_videos=standing.topic_max_videos
            if topic_max_videos is None
            else topic_max_videos,
        )
        _check(changed)
        await store.put_loop_settings(conn, changed)
    return changed
