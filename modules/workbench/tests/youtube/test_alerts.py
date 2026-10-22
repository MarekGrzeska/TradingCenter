"""What gets handed over, and what happens when handing over fails. The rule with the quiet failure is the marker: written
after the alerts package has accepted the film and only then, because it is both the deduplication and the retry."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from youtube_data import alerts, store
from youtube_data.alerts import (
    EVENT_TYPE,
    Alerts,
    Publisher,
    Rejected,
    Unreachable,
    attributes_of,
    slug,
)
from youtube_data.analysis import Reading
from youtube_data.providers.base import VideoRef

from .builders import SEEDED_PROMPT_ID
from .harness import MARKETS, Rig

pytestmark = pytest.mark.db

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)


class RecordingPublisher:
    """The alerts package as this package uses it: an announcement, an event, and whatever it was told to do with them."""

    def __init__(self, fails: Exception | None = None, refuses_announcing: bool = False) -> None:
        self.fails = fails
        self.refuses_announcing = refuses_announcing
        self.sent: list[tuple[str, dict, str]] = []

    async def announce(self) -> None:
        if self.refuses_announcing:
            raise Unreachable("no answer")

    async def publish(self, *, source_key: str, attributes: dict, text: str) -> None:
        self.sent.append((source_key, attributes, text))
        if self.fails is not None:
            raise self.fails


def reading(score: int, **overrides) -> Reading:
    body = {
        "summary_pl": "Prowadzący uważa, że złoto wzrośnie.",
        "text": "## Tezy\n- złoto rośnie",
        "impact_score": score,
    }
    body.update(overrides)
    return Reading.model_validate(body)


async def read_film(pool, video_id: str, *, score: int, origin: str = "channel:UC1", simulated: bool = False) -> None:
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
        await store.upsert_films(conn, [store.Discovery(ref, origin, SEEDED_PROMPT_ID)])
        await conn.execute("UPDATE videos SET state = 'transcribed' WHERE video_id = $1", video_id)
        await store.save_reading(
            conn,
            video_id,
            prompt_id=SEEDED_PROMPT_ID,
            prompt_version=1,
            reading=reading(score),
            model="m",
            simulated=simulated,
        )


def handing(pool, publisher, *, window_hours: int = 48) -> Alerts:
    return Alerts(
        pool,
        publisher,  # type: ignore[arg-type]
        batch_limit=10,
        window=timedelta(hours=window_hours),
    )


async def state_of(pool, video_id: str) -> str:
    async with pool.acquire() as conn:
        return (await store.get_video(conn, video_id)).state  # type: ignore[union-attr]


async def test_every_read_film_is_handed_over_whatever_its_score_because_the_rules_are_the_alerts_packages(pool) -> None:
    await read_film(pool, "v1", score=2)
    publisher = RecordingPublisher()

    await handing(pool, publisher).run(NOW)

    assert [key for key, _, _ in publisher.sent] == ["v1"]
    assert await state_of(pool, "v1") == "notified"


async def test_a_film_is_handed_over_once_and_a_refused_one_is_tried_again(pool) -> None:
    await read_film(pool, "v1", score=9)
    down = RecordingPublisher(fails=Unreachable("no answer"))
    announcer = handing(pool, down)

    await announcer.run(NOW)
    assert await state_of(pool, "v1") == "analysed", "no marker until the alerts package said yes"
    assert announcer.telling is False

    fine = RecordingPublisher()
    await handing(pool, fine).run(NOW)
    await handing(pool, fine).run(NOW)
    assert len(fine.sent) == 1
    assert await state_of(pool, "v1") == "notified"


async def test_a_film_no_model_has_read_is_published_as_nothing(pool) -> None:
    ref = VideoRef(
        video_id="unread",
        channel_id="UC1",
        channel_title="Gold Talk",
        title="Gold to 3000?",
        published_at=NOW - timedelta(hours=2),
        simulated=False,
    )
    async with pool.acquire() as conn:
        await store.upsert_films(conn, [store.Discovery(ref, "channel:UC1", SEEDED_PROMPT_ID)])
    publisher = RecordingPublisher()

    assert await handing(pool, publisher).run(NOW) == 0
    assert publisher.sent == []


async def test_a_film_the_alerts_package_refused_does_not_hold_up_the_films_behind_it(pool) -> None:
    await read_film(pool, "v1", score=9)
    await read_film(pool, "v2", score=9)

    class RefusesTheFirst(RecordingPublisher):
        async def publish(self, *, source_key: str, attributes: dict, text: str) -> None:
            await super().publish(source_key=source_key, attributes=attributes, text=text)
            if len(self.sent) == 1:
                raise Rejected("does not fit")

    publisher = RefusesTheFirst()
    one_at_a_time = Alerts(pool, publisher, batch_limit=1, window=timedelta(hours=48))  # type: ignore[arg-type]

    assert await one_at_a_time.run(NOW) == 0
    assert await one_at_a_time.run(NOW) == 1
    assert len({key for key, _, _ in publisher.sent}) == 2


@pytest.mark.parametrize("failure", [Rejected("no such type"), Unreachable("no answer")])
async def test_an_alerts_package_that_says_no_costs_the_film_its_turn_and_nothing_else(pool, failure) -> None:
    await read_film(pool, "v1", score=9)
    publisher = RecordingPublisher(fails=failure)

    assert await handing(pool, publisher).run(NOW) == 0

    assert await state_of(pool, "v1") == "analysed"


async def test_nothing_is_handed_over_until_the_type_is_announced(pool) -> None:
    await read_film(pool, "v1", score=9)
    publisher = RecordingPublisher(refuses_announcing=True)
    announcer = handing(pool, publisher)

    assert await announcer.run(NOW) == 0
    assert publisher.sent == [] and announcer.telling is False

    publisher.refuses_announcing = False
    assert await announcer.run(NOW) == 1
    assert announcer.telling is True


async def test_a_film_that_could_not_be_handed_over_in_time_is_let_go_not_announced_in_a_heap(pool) -> None:
    await read_film(pool, "v1", score=9)
    publisher = RecordingPublisher()

    await handing(pool, publisher, window_hours=48).run(datetime.now(UTC) + timedelta(days=3))

    assert publisher.sent == []
    assert await state_of(pool, "v1") == "quiet"


async def test_no_alerts_package_is_a_working_configuration_and_says_nothing(pool) -> None:
    rig = Rig(pool)

    assert alerts.build(pool, rig.settings, None) is None
    assert alerts.build(pool, rig.settings, httpx.AsyncClient()) is not None, "who is told is the operator's rules"


def test_a_channel_is_one_word_of_the_attribute() -> None:
    assert slug("Gold Talk") == "gold-talk"
    assert slug("Łukasz — Rynki") == "ukasz-rynki"
    assert slug("???") == "unknown"


async def test_a_film_carries_the_channel_the_topic_and_the_score_a_rule_filters_by(pool) -> None:
    async with pool.acquire() as conn:
        topic = await conn.fetchval(
            "INSERT INTO topics (phrase, language, interval_minutes, max_videos_per_run, added_by) "
            "VALUES ('gold outlook', '', 60, 3, 'operator') RETURNING id"
        )
    await read_film(pool, "v1", score=9, origin=f"topic:{topic}")
    publisher = RecordingPublisher()

    await handing(pool, publisher).run(NOW)

    [(_, attributes, _)] = publisher.sent
    assert (attributes["channel"], attributes["channel_slug"], attributes["topic"], attributes["impact_score"]) == (
        "Gold Talk",
        "gold-talk",
        "gold outlook",
        9,
    )
    assert attributes["prompt"] == "Rynkowy" and attributes["url"].endswith("v1")
    assert "instruments" not in attributes


async def test_the_whole_road_hands_over_every_read_film_once(pool) -> None:
    rig = Rig(pool)
    publisher = RecordingPublisher()
    rig.announcing_to(publisher)
    await rig.tick()  # nothing followed yet
    from youtube_data import watchlist

    await watchlist.follow_channel(pool, rig.providers.source, rig.settings, MARKETS, added_by="operator")
    rig.clock.advance(minutes=25)  # simfilm0004, the emergency cut, has been published

    await rig.tick()
    await rig.tick()

    keys = [key for key, _, _ in publisher.sent]
    assert len(keys) == len(set(keys)) >= 1
    loud = next(text for key, _, text in publisher.sent if key == "simfilm0004")
    assert "Wpływ 9/10" in loud and "simfilm0004" in loud
    assert loud.startswith("[SYMULACJA"), "a film that does not exist says so on its first line"


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
        audio_language=None,
        prompt_id=SEEDED_PROMPT_ID,
        state="analysed",
        skip_reason=None,
        attempts=0,
        next_attempt_at=None,
        reading_failures=0,
        simulated=False,
        discovered_at=NOW,
        notified_at=None,
    )
    return store.ToAnnounce(stored, reading(9, **overrides).model_dump(mode="json"), simulated=False, prompt="Rynkowy")


def test_a_message_names_the_channel_the_score_and_the_way_to_the_film() -> None:
    text = alerts.message(_item())

    assert "Wpływ 9/10 — Gold Talk" in text
    assert text.endswith("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert "SYMULACJA" not in text


def test_a_long_summary_is_cut_by_this_package_so_the_door_never_has_to_refuse_it() -> None:
    long = "Bardzo długie streszczenie. " * 400

    text = alerts.message(_item(summary_pl=long), limit=1200)

    assert len(text) <= 1200
    assert "…" in text
    assert text.endswith("watch?v=dQw4w9WgXcQ"), "the link is what a cut must not take"


def test_a_title_nobody_bounded_is_cut_too_and_the_message_stays_under_the_doors_ceiling() -> None:
    item = _item(summary_pl="Krótko.")
    item = replace(item, video=replace(item.video, title="Złoto " * 2000, channel_title="Kanał " * 500))

    text = alerts.message(item)

    assert len(text) <= alerts.MESSAGE_CHARS
    assert text.endswith("watch?v=dQw4w9WgXcQ")


def test_a_simulated_film_read_by_a_real_model_is_still_announced_as_a_simulation() -> None:
    item = _item()

    assert "SYMULACJA" in alerts.message(replace(item, video=replace(item.video, simulated=True)))
    assert attributes_of(replace(item, simulated=True))["simulated"] is True


async def test_the_publisher_posts_the_event_and_says_why_it_was_refused() -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        if len(seen) == 1:
            return httpx.Response(200, json={"id": 1, "duplicate": False, "fires": 0})
        return httpx.Response(422, json={"detail": {"detail": "nobody has announced an event type"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://alerts") as client:
        publisher = Publisher(client)
        await publisher.publish(source_key="v1", attributes={"channel": "x"}, text="hello")
        with pytest.raises(Rejected, match="nobody has announced"):
            await publisher.publish(source_key="v2", attributes={}, text="again")

    assert seen[0] == {"type": EVENT_TYPE, "source_key": "v1", "attributes": {"channel": "x"}, "text": "hello"}


async def test_an_alerts_package_that_does_not_answer_is_not_a_hand_over() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://alerts") as client:
        with pytest.raises(Unreachable):
            await Publisher(client).publish(source_key="v1", attributes={}, text="hello")


async def test_a_film_named_by_hand_ends_quiet_because_whoever_asked_is_already_looking(pool) -> None:
    await read_film(pool, "v1", score=9, origin="manual")
    publisher = RecordingPublisher()

    await handing(pool, publisher).run(NOW)

    assert publisher.sent == []
    assert await state_of(pool, "v1") == "quiet"


async def test_a_reading_ordered_by_another_prompt_is_never_the_one_handed_over(pool) -> None:
    await read_film(pool, "v1", score=3)
    async with pool.acquire() as conn:
        other = await store.create_prompt(conn, name="Technical", body="Levels only.")
        await store.save_reading(
            conn,
            "v1",
            prompt_id=other.id,
            prompt_version=1,
            reading=reading(10),
            model="m",
            simulated=False,
        )
    publisher = RecordingPublisher()

    await handing(pool, publisher).run(NOW)

    [(_, attributes, _)] = publisher.sent
    assert (attributes["impact_score"], attributes["prompt"]) == (3, "Rynkowy")
