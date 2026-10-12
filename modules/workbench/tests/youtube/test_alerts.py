"""What gets said, and what happens when saying it fails. The rule with the quiet failure is the marker: written after a
success and only then, because the gateway keeps no history and the marker is both the deduplication and the retry."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from youtube_data import alerts, store
from youtube_data.alerts import Alerts, Gateway, GatewayRefused, GatewayUnreachable
from youtube_data.analysis import Reading
from youtube_data.providers.base import VideoRef

from .harness import MARKETS, Rig

pytestmark = pytest.mark.db

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)


class RecordingGateway:
    """The door to Telegram as this package uses it: one call, and whatever it was told to do with it."""

    def __init__(self, fails: Exception | None = None) -> None:
        self.fails = fails
        self.sent: list[tuple[str, str]] = []

    async def send(self, *, destination: str, text: str) -> None:
        self.sent.append((destination, text))
        if self.fails is not None:
            raise self.fails


def reading(score: int, **overrides) -> Reading:
    body = {
        "summary_pl": "Prowadzący uważa, że złoto wzrośnie.",
        "key_points": [],
        "instruments": [{"name": "Gold", "epic": "GOLD", "sentiment": "bullish", "conviction": 4, "horizon": "swing"}],
        "predictions": [],
        "topics": [],
        "impact_score": score,
    }
    body.update(overrides)
    return Reading.model_validate(body)


async def read_film(pool, video_id: str, *, score: int, rule: str = "threshold", simulated: bool = False) -> None:
    """A film that has been read and awaits the last step, without a loop having got it there."""
    ref = VideoRef(
        video_id=video_id,
        channel_id="UC1",
        channel_title="Gold Talk",
        title="Gold to 3000?",
        published_at=NOW - timedelta(hours=2),
        simulated=simulated,
    )
    async with pool.acquire() as conn:
        await store.upsert_films(conn, [store.Discovery(ref, "channel:UC1", "market", rule)])
        await store.save_reading(conn, video_id, profile="market", reading=reading(score), model="m", simulated=simulated)


def announcing(pool, gateway, *, min_score: int = 8, window_hours: int = 48) -> Alerts:
    return Alerts(
        pool,
        gateway,  # type: ignore[arg-type]
        destination="operator",
        min_score=min_score,
        batch_limit=10,
        window=timedelta(hours=window_hours),
    )


async def state_of(pool, video_id: str) -> str:
    async with pool.acquire() as conn:
        return (await store.get_video(conn, video_id)).state  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("rule", "score", "told"),
    [("always", 2, True), ("threshold", 8, True), ("threshold", 7, False), ("never", 10, False)],
)
async def test_what_a_channel_asked_for_decides_whether_a_film_is_announced(pool, rule, score, told) -> None:
    await read_film(pool, "v1", score=score, rule=rule)
    gateway = RecordingGateway()

    await announcing(pool, gateway).run(NOW)

    assert len(gateway.sent) == (1 if told else 0)
    assert await state_of(pool, "v1") == ("notified" if told else "quiet")


async def test_a_film_is_announced_once_and_a_failed_delivery_is_tried_again(pool) -> None:
    await read_film(pool, "v1", score=9)
    down = RecordingGateway(fails=GatewayUnreachable("no answer"))

    await announcing(pool, down).run(NOW)
    assert await state_of(pool, "v1") == "analysed", "no marker until the gateway said yes"

    fine = RecordingGateway()
    await announcing(pool, fine).run(NOW)
    await announcing(pool, fine).run(NOW)
    assert len(fine.sent) == 1
    assert await state_of(pool, "v1") == "notified"


@pytest.mark.parametrize("failure", [GatewayRefused("rate limited: wait 30 s"), GatewayUnreachable("no answer")])
async def test_a_gateway_that_says_no_costs_the_film_its_turn_and_nothing_else(pool, failure) -> None:
    await read_film(pool, "v1", score=9)
    await read_film(pool, "v2", score=3)  # quiet either way
    gateway = RecordingGateway(fails=failure)

    assert await announcing(pool, gateway).run(NOW) == 0

    assert await state_of(pool, "v1") == "analysed"
    assert await state_of(pool, "v2") == "quiet"


async def test_a_film_the_gateway_could_not_announce_in_time_is_let_go_not_announced_in_a_heap(pool) -> None:
    await read_film(pool, "v1", score=9)
    gateway = RecordingGateway()

    await announcing(pool, gateway, window_hours=48).run(datetime.now(UTC) + timedelta(days=3))

    assert gateway.sent == []
    assert await state_of(pool, "v1") == "quiet"


async def test_no_destination_is_a_working_configuration_and_says_nothing(pool) -> None:
    rig = Rig(pool)

    assert alerts.build(pool, rig.settings, None) is None
    assert alerts.build(pool, rig.settings, httpx.AsyncClient()) is None, "a client but no adresat"


async def test_the_whole_road_announces_a_loud_film_once_and_a_quiet_one_never(pool) -> None:
    rig = Rig(pool)
    gateway = RecordingGateway()
    rig.announcing_to(gateway)
    await rig.tick()  # nothing followed yet
    from youtube_data import watchlist

    await watchlist.follow_channel(pool, rig.providers.source, rig.settings, MARKETS, added_by="operator")
    rig.clock.advance(minutes=25)  # simfilm0004, the emergency cut, has been published

    await rig.tick()
    await rig.tick()

    assert len(gateway.sent) == 1
    destination, text = gateway.sent[0]
    assert destination == "operator"
    assert "Wpływ 9/10" in text and "simfilm0004" in text
    assert text.startswith("[SYMULACJA"), "a film that does not exist says so on its first line"
    states = await rig.states()
    assert states["simfilm0004"] == "notified" and states["simfilm0002"] == "quiet"


def _item(**overrides) -> store.ToAnnounce:
    video = VideoRef(
        video_id="dQw4w9WgXcQ",
        channel_id="UC1",
        channel_title="Gold Talk",
        title="Gold to 3000?",
        published_at=NOW,
    )
    stored = store.Video(
        video_id=video.video_id,
        channel_id=video.channel_id,
        channel_title=video.channel_title,
        title=video.title,
        published_at=video.published_at,
        duration_seconds=600,
        live_status="none",
        origins=("channel:UC1",),
        profile="market",
        alert_rule="threshold",
        state="analysed",
        skip_reason=None,
        attempts=0,
        next_attempt_at=None,
        reading_failures=0,
        job_provider=None,
        job_id=None,
        simulated=False,
        discovered_at=NOW,
        notified_at=None,
    )
    return store.ToAnnounce(stored, reading(9, **overrides).model_dump(mode="json"), simulated=False)


def test_a_message_names_the_channel_the_views_and_the_way_to_the_film() -> None:
    text = alerts.message(_item())

    assert "Wpływ 9/10 — Gold Talk" in text
    assert "Gold ▲ (4/5, swing)" in text
    assert text.endswith("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert "SYMULACJA" not in text


def test_a_long_summary_is_cut_by_this_package_so_the_gateway_never_has_to_refuse_it() -> None:
    long = "Bardzo długie streszczenie. " * 400

    text = alerts.message(_item(summary_pl=long), limit=1200)

    assert len(text) <= 1200
    assert "…" in text
    assert text.endswith("watch?v=dQw4w9WgXcQ"), "the link is what a cut must not take"


def test_a_title_nobody_bounded_is_cut_too_and_the_message_stays_under_the_gateways_ceiling() -> None:
    item = _item(summary_pl="Krótko.")
    item = replace(item, video=replace(item.video, title="Złoto " * 2000, channel_title="Kanał " * 500))

    text = alerts.message(item)

    assert len(text) <= alerts.MESSAGE_CHARS
    assert text.endswith("watch?v=dQw4w9WgXcQ")


def test_a_simulated_film_read_by_a_real_model_is_still_announced_as_a_simulation() -> None:
    item = _item()

    assert "SYMULACJA" in alerts.message(replace(item, video=replace(item.video, simulated=True)))


async def test_the_gateway_client_posts_the_destination_and_says_why_it_was_refused() -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen.append(json.loads(request.content))
        if len(seen) == 1:
            return httpx.Response(200, json={})
        return httpx.Response(429, json={"detail": {"detail": "wait 30 seconds"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://door") as client:
        gateway = Gateway(client)
        await gateway.send(destination="operator", text="hello")
        with pytest.raises(GatewayRefused, match="wait 30 seconds"):
            await gateway.send(destination="operator", text="again")

    assert seen[0] == {"destination": "operator", "text": "hello"}


async def test_a_gateway_that_does_not_answer_is_not_a_delivery() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://door") as client:
        with pytest.raises(GatewayUnreachable):
            await Gateway(client).send(destination="operator", text="hello")
