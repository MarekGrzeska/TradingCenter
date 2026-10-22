"""The operator's interval and topic limits: that they reach the wire, that they are checked, and that the loop and a new
topic obey what was saved."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from tc_runtime.liveness import LoopHeartbeat

from youtube_data import loop_settings, watchlist
from youtube_data.ingest import Ingest

from .harness import Rig

pytestmark = pytest.mark.db


@pytest.fixture
async def rig(pool) -> Rig:
    return Rig(
        pool,
        poll_interval_seconds=1800,
        topic_default_interval_minutes=360,
        topic_default_max_videos=3,
    )


@pytest.fixture
async def api(app, rig):
    app.state.pool = rig.pool
    app.state.settings = rig.settings
    app.state.ingest = rig.ingest
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://tests"
    ) as client:
        yield client


async def test_nothing_saved_reads_as_the_process_settings_and_a_save_changes_only_what_was_given(
    api,
) -> None:
    before = (await api.get("/settings")).json()
    assert before["saved"] is False
    assert (
        before["poll_interval_minutes"],
        before["topic_interval_minutes"],
        before["topic_max_videos"],
    ) == (30, 360, 3)

    after = (await api.patch("/settings", json={"poll_interval_minutes": 10})).json()

    assert after["saved"] is True
    assert (
        after["poll_interval_minutes"],
        after["topic_interval_minutes"],
        after["topic_max_videos"],
    ) == (10, 360, 3)
    assert (await api.get("/settings")).json() == after


@pytest.mark.parametrize(
    "body",
    [
        {"poll_interval_minutes": 4},
        {"topic_interval_minutes": 14},
        {"topic_max_videos": 21},
        {"topic_max_videos": 0},
    ],
)
async def test_a_value_outside_the_limits_is_refused_and_nothing_changes(api, body) -> None:
    refused = await api.patch("/settings", json=body)

    assert refused.status_code == 422 and refused.json()["detail"]["cause"] == "request"
    assert (await api.get("/settings")).json()["saved"] is False


async def test_a_topic_added_without_limits_gets_the_saved_ones_and_a_topic_on_the_list_keeps_its_own(
    rig, pool
) -> None:
    old = await watchlist.add_topic(pool, rig.settings, "gold", added_by="operator")
    await loop_settings.update(pool, rig.settings, topic_interval_minutes=120, topic_max_videos=7)

    new = await watchlist.add_topic(pool, rig.settings, "silver", added_by="agent")

    assert (new.topic.interval_minutes, new.topic.max_videos_per_run) == (120, 7)
    assert new.defaults_applied == ("interval_minutes", "max_videos_per_run")
    again = await watchlist.add_topic(pool, rig.settings, "gold", added_by="operator")
    assert (again.topic.interval_minutes, again.topic.max_videos_per_run) == (
        old.topic.interval_minutes,
        old.topic.max_videos_per_run,
    )


async def test_the_loop_reads_the_saved_interval_and_the_heartbeat_follows_it(rig, pool) -> None:
    heartbeat = LoopHeartbeat("ingest", expected_seconds=1800)
    ingest = Ingest(pool, rig.providers, rig.settings, heartbeat=heartbeat)
    assert await ingest._interval() == 1800

    await loop_settings.update(pool, rig.settings, poll_interval_minutes=10)

    assert await ingest._interval() == 600 and heartbeat.expected_seconds == 600


async def test_a_wait_in_progress_is_ended_by_a_shorter_interval_and_not_by_nothing(
    rig, monkeypatch
) -> None:
    ingest = rig.ingest
    resting = asyncio.create_task(ingest._rest(3600))
    await asyncio.sleep(0.05)
    assert not resting.done()

    async def shortened() -> float:
        return 0.0

    monkeypatch.setattr(ingest, "_interval", shortened)
    ingest.interval_changed()

    await asyncio.wait_for(resting, timeout=2)
