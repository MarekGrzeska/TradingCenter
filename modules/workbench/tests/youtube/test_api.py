"""The contract over HTTP: that the state reaches the wire, and that a refusal says why. One test per route or two, not the
whole matrix — windows, filters and ceilings are tested where the rules live."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from tc_runtime.liveness import LoopHeartbeat

from youtube_data import store

from .harness import GOLD, MARKETS, Rig

pytestmark = pytest.mark.db


@pytest.fixture
async def rig(pool) -> Rig:
    return Rig(pool)


@pytest.fixture
async def api(app, rig):
    """The application over a real database and the simulated providers, with the lifespan bypassed: it would start a loop."""
    app.state.pool = rig.pool
    app.state.settings = rig.settings
    app.state.providers = rig.providers
    app.state.alerts = None
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://tests") as client:
        yield client


async def followed_and_read(api, rig: Rig, *channels: str) -> None:
    for channel in channels:
        assert (await api.post("/channels", json={"reference": channel})).status_code == 200
    await rig.tick()


# --- films ----------------------------------------------------------------------------------------------------------


async def test_a_read_film_reaches_the_wire_with_its_reading_and_an_unread_one_with_the_field_empty(api, rig) -> None:
    await followed_and_read(api, rig, GOLD)

    body = (await api.get("/videos", params={"hours": 24})).json()

    films = {film["video_id"]: film for film in body["videos"]}
    read = films["simfilm0001"]
    assert read["reading"]["impact_score"] == 6 and read["reading"]["simulated"] is True
    assert read["reading"]["model"] == "sim" and read["simulated"] is True
    assert read["url"].endswith("simfilm0001")
    assert "reading" in films["simfilm0008"] and films["simfilm0008"]["reading"] is None
    assert body["count"] == len(body["videos"])
    assert all("transcript" not in film and "content" not in film for film in body["videos"])


async def test_a_list_can_be_narrowed_by_what_a_reading_says(api, rig) -> None:
    await followed_and_read(api, rig, GOLD, MARKETS)

    by_instrument = (await api.get("/videos", params={"instrument": "GOLD"})).json()["videos"]
    by_score = (await api.get("/videos", params={"min_score": 6})).json()["videos"]
    by_channel = (await api.get("/videos", params={"channel_id": MARKETS})).json()["videos"]

    assert [film["video_id"] for film in by_instrument] == ["simfilm0001"]
    assert {film["video_id"] for film in by_score} == {"simfilm0001"}
    assert {film["channel_id"] for film in by_channel} == {MARKETS}


async def test_a_window_that_ends_before_it_starts_is_refused_with_the_reason(api) -> None:
    now = datetime.now(UTC)

    response = await api.get(
        "/videos", params={"since": now.isoformat(), "until": (now - timedelta(hours=1)).isoformat()}
    )

    assert response.status_code == 422
    assert "ends before it starts" in response.json()["detail"]["detail"]
    assert (await api.get("/videos", params={"state": "sleeping"})).status_code == 422
    # A bound with no zone beside the aware "now" is a refusal, not a comparison that raises.
    assert (await api.get("/videos", params={"since": "2099-01-01T00:00:00"})).status_code == 422


async def test_a_film_is_read_whole_and_its_transcript_a_page_at_a_time(api, rig) -> None:
    await followed_and_read(api, rig, GOLD)

    film = await api.get("/videos/simfilm0001")
    first = (await api.get("/videos/simfilm0001/transcript", params={"limit": 100})).json()
    last = (await api.get("/videos/simfilm0001/transcript", params={"offset": first["total_chars"] - 5})).json()

    assert film.json()["state"] == "quiet"
    assert len(first["text"]) == 100 and first["next_offset"] == 100 and first["simulated"] is True
    assert last["next_offset"] is None and len(last["text"]) == 5
    assert (await api.get("/videos/nothing")).status_code == 404
    assert (await api.get("/videos/simfilm0005/transcript")).status_code == 404


async def test_a_film_named_by_hand_is_queued_and_a_non_film_is_refused(api, rig) -> None:
    rig.clock.advance(minutes=30)

    queued = await api.post("/videos", json={"reference": "https://youtu.be/simfilm0004"})
    refused = await api.post("/videos", json={"reference": "https://example.com/x"})

    assert queued.json() == {"video_id": "simfilm0004", "title": queued.json()["title"], "created": True}
    assert refused.status_code == 422 and refused.json()["detail"]["cause"] == "request"


# --- the watch list -------------------------------------------------------------------------------------------------


async def test_a_channel_is_followed_paused_and_taken_off(api) -> None:
    added = await api.post("/channels", json={"reference": "@simzloto", "language": "pl"})
    again = await api.post("/channels", json={"reference": GOLD, "language": "de"})

    assert added.json()["created"] is True and again.json()["created"] is False
    assert again.json()["channel"]["language"] == "pl", "following again does not change what was set"

    paused = await api.patch(f"/channels/{GOLD}", json={"active": False})
    assert paused.json()["active"] is False
    listed = (await api.get("/channels")).json()
    assert listed["ceiling"] == 100 and [c["channel_id"] for c in listed["channels"]] == [GOLD]

    assert (await api.delete(f"/channels/{GOLD}")).status_code == 204
    assert (await api.delete(f"/channels/{GOLD}")).status_code == 404


async def test_a_channel_that_does_not_exist_and_a_list_that_is_full_are_refused_with_the_reason(api, rig) -> None:
    unknown = await api.post("/channels", json={"reference": "@nobody-here"})
    assert unknown.status_code == 422 and "no channel" in unknown.json()["detail"]["detail"]

    rig.settings = rig.settings.model_copy(update={"max_channels": 1})
    api._transport.app.state.settings = rig.settings  # type: ignore[attr-defined]
    await api.post("/channels", json={"reference": "@simzloto"})
    full = await api.post("/channels", json={"reference": "@simmarkets"})
    assert full.status_code == 422 and "ceiling" in full.json()["detail"]["detail"]


async def test_a_topic_says_which_of_its_limits_came_from_the_settings(api) -> None:
    added = await api.post("/topics", json={"phrase": "gold outlook"})
    body = added.json()

    assert body["created"] is True
    assert body["defaults_applied"] == ["interval_minutes", "max_videos_per_run"]
    topic_id = body["topic"]["id"]
    assert (await api.patch(f"/topics/{topic_id}", json={"active": False})).json()["active"] is False
    assert "search_supported" not in (await api.get("/topics")).json()
    assert (await api.delete(f"/topics/{topic_id}")).status_code == 204
    assert (await api.post("/topics", json={"phrase": " "})).status_code == 422


# --- state ----------------------------------------------------------------------------------------------------------


async def test_the_state_says_what_the_screen_must_know_before_it_says_no_films(api, rig) -> None:
    await followed_and_read(api, rig, GOLD)
    async with rig.pool.acquire() as conn:
        await store.note_provider(conn, "sim", ok=False, at=rig.clock.now() + timedelta(minutes=1), reason="IpBlocked")

    body = (await api.get("/state")).json()

    assert body["simulating"] is True and body["model_configured"] is True
    assert body["alerts_configured"] is False
    assert body["channels_active"] == 1
    roles = {(p["role"], p["name"], p["unit"]) for p in body["providers"]}
    assert roles == {
        ("source", "sim", "sim_units"),
        ("transcripts", "sim", "sim_video_seconds"),
        ("analyser", "analyser", "tokens"),
    }
    transcripts = next(p for p in body["providers"] if p["role"] == "transcripts")
    assert transcripts["blocked"] is True and transcripts["blocked_reason"] == "IpBlocked"
    assert transcripts["spent_today"] > 0 and transcripts["exhausted"] is False
    assert body["recent"]["quiet"] >= 1 and body["recent_days"] == 7


async def test_a_loop_that_has_stopped_is_called_stale_and_a_failed_pass_is_not_a_pass(app, api) -> None:
    async def state() -> dict:
        return (await api.get("/state")).json()

    assert (await state())["loop"] is None

    started = datetime.now(UTC) - timedelta(seconds=1800 * 10)
    app.state.heartbeats = type("H", (), {"__getitem__": lambda self, name: LoopHeartbeat(name, expected_seconds=1800, started=started)})()
    stale = await state()
    assert stale["stale"] is True and stale["loop"]["ran"] is False and stale["loop"]["passes_late"] > 3
