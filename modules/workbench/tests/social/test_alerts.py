"""What gets handed over, and what happens when handing over fails.

The rule with the quiet failure is the marker: written after the alerts package has accepted the post and only then,
because this column is both the deduplication and the whole retry mechanism.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from social_data import alerts, store
from social_data.alerts import (
    EVENT_TYPE,
    Alerts,
    Publisher,
    Rejected,
    Unreachable,
    attributes_of,
    slug,
)
from social_data.ingest import Ingest

from .builders import TRUTH_SOCIAL, raw_post
from .fakes import FakeSource

pytestmark = pytest.mark.db

SINCE = datetime.now(UTC) - timedelta(hours=24)


class RecordingPublisher:
    """The alerts package as this module uses it: an announcement, an event, and whatever it was told to do with them."""

    def __init__(self, fails: Exception | None = None, refuses_announcing: bool = False) -> None:
        self._fails = fails
        self.refuses_announcing = refuses_announcing
        self.announced = 0
        self.sent: list[tuple[str, dict, str]] = []

    async def announce(self) -> None:
        self.announced += 1
        if self.refuses_announcing:
            raise Unreachable("no answer")

    async def publish(self, *, source_key: str, attributes: dict, text: str) -> None:
        self.sent.append((source_key, attributes, text))
        if self._fails is not None:
            raise self._fails


async def _post(pool, external_id: str, *, score: int | None, content: str = "TARIFFS.") -> int:
    async with pool.acquire() as conn:
        await store.insert_new_posts(
            conn, [raw_post(external_id, content=content, minutes_ago=5)]
        )
        stored = await store.post_by_external_id(conn, TRUTH_SOCIAL, external_id)
        assert stored is not None
        if score is not None:
            await store.save_analysis(
                conn, stored.id, topics=("tariffs",), score=score, model="analyst"
            )
    return stored.id


def _alerts(pool, publisher) -> Alerts:
    return Alerts(pool, publisher)  # type: ignore[arg-type]


async def test_a_post_is_handed_over_once_with_what_a_rule_filters_by(pool) -> None:
    post_id = await _post(pool, "loud", score=9)
    publisher = RecordingPublisher()
    handing = _alerts(pool, publisher)

    assert await handing.run(SINCE) == 1
    assert await handing.run(SINCE) == 0

    [(key, attributes, text)] = publisher.sent
    assert key == str(post_id)
    assert (attributes["author_slug"], attributes["impact_score"], attributes["topics"]) == (
        "realdonaldtrump",
        9,
        ["tariffs"],
    )
    assert "9/10" in text
    async with pool.acquire() as conn:
        assert await conn.fetchval("SELECT notified_at FROM posts WHERE id = $1", post_id)


async def test_a_post_of_any_score_is_handed_over_because_the_threshold_is_a_rule_now(pool) -> None:
    await _post(pool, "quiet", score=3)
    publisher = RecordingPublisher()

    assert await _alerts(pool, publisher).run(SINCE) == 1
    assert publisher.sent[0][1]["impact_score"] == 3


async def test_a_post_no_model_has_read_is_not_handed_over(pool) -> None:
    """An absent score is not a low one. Handing it over "just in case" would let it through every rule's threshold in the
    state this module knows least about."""
    await _post(pool, "unread", score=None)
    publisher = RecordingPublisher()

    assert await _alerts(pool, publisher).run(SINCE) == 0
    assert publisher.sent == []


@pytest.mark.parametrize(
    "failure",
    [Rejected("the alerts package refused the event: no type"), Unreachable("no answer")],
    ids=["refused", "unreachable"],
)
async def test_a_failed_hand_over_leaves_no_marker_and_the_next_pass_retries(
    pool, failure: Exception
) -> None:
    post_id = await _post(pool, "loud", score=9)
    failing = RecordingPublisher(fails=failure)
    handing = _alerts(pool, failing)

    assert await handing.run(SINCE) == 0
    assert handing.telling is False
    async with pool.acquire() as conn:
        assert await conn.fetchval("SELECT notified_at FROM posts WHERE id = $1", post_id) is None

    working = RecordingPublisher()
    assert await _alerts(pool, working).run(SINCE) == 1
    assert len(working.sent) == 1


async def test_one_post_failing_does_not_stop_the_rest(pool) -> None:
    await _post(pool, "first", score=9)
    await _post(pool, "second", score=10)

    class FailsTheFirst(RecordingPublisher):
        async def publish(self, *, source_key: str, attributes: dict, text: str) -> None:
            self.sent.append((source_key, attributes, text))
            if len(self.sent) == 1:
                raise Unreachable("no answer")

    publisher = FailsTheFirst()
    assert await _alerts(pool, publisher).run(SINCE) == 1
    assert len(publisher.sent) == 2


async def test_nothing_is_handed_over_until_the_type_is_announced_and_the_state_says_so(pool) -> None:
    await _post(pool, "loud", score=9)
    publisher = RecordingPublisher(refuses_announcing=True)
    handing = _alerts(pool, publisher)

    assert await handing.run(SINCE) == 0

    assert publisher.sent == [] and handing.telling is False
    publisher.refuses_announcing = False
    assert await handing.run(SINCE) == 1
    assert handing.telling is True


def test_the_message_carries_the_reading_and_where_to_read_the_rest() -> None:
    from social_data.models import Post

    post = Post(
        id=1,
        source=TRUTH_SOCIAL,
        external_id="1",
        author="realDonaldTrump",
        content="word " * 400,
        published_at=datetime.now(UTC),
        fetched_at=datetime.now(UTC),
        url="https://trumpstruth.org/statuses/1",
        topics=("tariffs", "china"),
        impact_score=9,
        analysed_model="analyst",
        analysed_at=datetime.now(UTC),
    )

    text = alerts.message(post)

    assert text.startswith("Impact 9/10 — realDonaldTrump")
    assert "tariffs, china" in text
    assert post.url in text
    # Cut here rather than at Telegram, which refuses a message over its own ceiling outright.
    assert len(text) < 4096
    assert "…" in text


def a_post(**overrides):
    from social_data.models import Post

    fields = {
        "id": 1,
        "source": TRUTH_SOCIAL,
        "external_id": "1",
        "author": "realDonaldTrump",
        "content": "The United States is striking Iranian targets.",
        "published_at": datetime.now(UTC),
        "fetched_at": datetime.now(UTC),
        "url": "https://trumpstruth.org/statuses/1",
        "topics": ("tariffs",),
        "impact_score": 9,
        "analysed_model": "analyst",
        "analysed_at": datetime.now(UTC),
    }
    fields.update(overrides)
    return Post(**fields)


class TestTheMessageSpeaksPolish:
    """The notification is the one place the translation is used with no terminal to fall back to.
    It carried the original for as long as this module has existed, which threw away the reading
    it had paid a model for — found on production, 1 September 2026, on a post scored 10."""

    def test_the_translation_is_what_the_operator_reads(self) -> None:
        post = a_post(
            content="The United States is striking Iranian targets.",
            translated_content="Stany Zjednoczone atakują irańskie cele.",
            translated_model="gpt-6-luna",
            translated_at=datetime.now(UTC),
        )

        text = alerts.message(post)

        assert "Stany Zjednoczone atakują irańskie cele." in text
        assert "The United States is striking" not in text

    def test_an_untranslated_post_falls_back_and_says_so(self) -> None:
        """Translation and analysis are separate readings and either can fail alone, so a scored
        post with no Polish is reachable. Silence there would read as an English post on purpose."""
        text = alerts.message(a_post(translated_content=None))

        assert "The United States is striking Iranian targets." in text
        assert "tłumaczenie nie dotarło" in text

    def test_a_translated_post_is_not_marked_as_a_fallback(self) -> None:
        text = alerts.message(a_post(translated_content="Cokolwiek."))

        assert "tłumaczenie nie dotarło" not in text

    def test_the_excerpt_is_cut_from_the_translation_not_the_original(self) -> None:
        """The ceiling is Telegram's and the gateway refuses rather than truncating, so cutting the
        wrong text would either overrun or shorten something nobody reads."""
        post = a_post(content="short", translated_content="słowo " * 400)

        text = alerts.message(post)

        assert len(text) < 4096
        assert "…" in text
        assert "short" not in text


class TestBuild:
    def test_no_alerts_package_is_a_supported_state(self, pool, settings) -> None:
        """Standalone, with no host to hand the package in: nobody can be told, and the module collects anyway."""
        assert alerts.build(pool, settings, None) is None

    def test_with_the_package_it_is_built_and_there_is_nothing_else_to_configure(self, pool, settings) -> None:
        assert alerts.build(pool, settings, httpx.AsyncClient()) is not None

    async def test_collection_is_untouched_where_there_is_no_alerts_package(self, pool) -> None:
        """A supported state rather than a fault: the archive collects exactly as it did and says nothing."""
        source = FakeSource([raw_post("collected", minutes_ago=5)])
        collecting = Ingest(pool, [source], interval_seconds=300, window_hours=24, announce=None)

        [result] = await collecting.tick()

        assert result.succeeded and result.inserted == 1
        async with pool.acquire() as conn:
            stored = await store.post_by_external_id(conn, TRUTH_SOCIAL, "collected")
            assert stored is not None
            assert (
                await conn.fetchval("SELECT notified_at FROM posts WHERE id = $1", stored.id)
            ) is None


class TestConfiguration:
    def _settings(self, settings, **overrides):
        from social_data.config import Settings

        return Settings(
            **{
                **settings.model_dump(),
                **overrides,
            },
            _env_file=None,
        )

    def test_a_threshold_outside_the_reading_range_is_refused(self, settings) -> None:
        with pytest.raises(ValueError) as err:
            self._settings(settings, alert_min_impact_score=11)
        assert "ALERT_MIN_IMPACT_SCORE" in str(err.value)


class TestTheWords:
    def test_an_author_is_one_word_of_the_attribute(self) -> None:
        assert slug("Donald J. Trump (@realDonaldTrump)") == "donald-j-trump-realdonaldtrump"
        assert slug("***") == "unknown"
        assert len(slug("x" * 200)) == 60

    def test_the_attributes_are_what_the_converted_rules_filter_on(self) -> None:
        attributes = attributes_of(a_post(translated_content="Cokolwiek."))

        assert {"author", "author_slug", "impact_score"} <= set(attributes)
        assert attributes["translated"] is True


class TestThePublisher:
    def _publisher(self, status_code: int, body: dict) -> Publisher:
        def answer(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code, json=body)

        return Publisher(httpx.AsyncClient(transport=httpx.MockTransport(answer), base_url="http://alerts"))

    async def test_a_refusal_is_in_the_alerts_packages_own_words(self) -> None:
        publisher = self._publisher(422, {"detail": {"detail": "nobody has announced an event type"}})

        with pytest.raises(Rejected, match="nobody has announced"):
            await publisher.publish(source_key="1", attributes={}, text="hi")

    async def test_the_type_is_announced_with_its_schema(self) -> None:
        seen: list[httpx.Request] = []

        def answer(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(204)

        await Publisher(httpx.AsyncClient(transport=httpx.MockTransport(answer), base_url="http://alerts")).announce()

        assert seen[0].url.path == f"/event-types/{EVENT_TYPE}"
        assert b"author_slug" in seen[0].content
