"""What gets said, and what happens when saying it fails.

The rule with the quiet failure is the marker: written after a success and only then, because the
gateway keeps no history and this column is both the deduplication and the whole retry mechanism.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from builders import TRUTH_SOCIAL, raw_post
from fakes import FakeSource

from social_data import alerts, store
from social_data.alerts import Alerts, GatewayRefused, GatewayUnreachable
from social_data.ingest import Ingest

pytestmark = pytest.mark.db

SINCE = datetime.now(UTC) - timedelta(hours=24)


class RecordingGateway:
    """The gateway as this module uses it: one call, and whatever it was told to do with it."""

    def __init__(self, fails: Exception | None = None) -> None:
        self._fails = fails
        self.sent: list[tuple[str, str]] = []

    async def send(self, *, destination: str, text: str) -> None:
        self.sent.append((destination, text))
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


def _alerts(pool, gateway, *, min_score: int = 8) -> Alerts:
    return Alerts(pool, gateway, destination="operator", min_score=min_score)  # type: ignore[arg-type]


async def test_a_post_over_the_threshold_is_announced_once(pool) -> None:
    post_id = await _post(pool, "loud", score=9)
    gateway = RecordingGateway()
    announcing = _alerts(pool, gateway)

    assert await announcing.run(SINCE) == 1
    assert await announcing.run(SINCE) == 0

    [(destination, text)] = gateway.sent
    assert destination == "operator"
    assert "9/10" in text
    async with pool.acquire() as conn:
        assert await store.post_by_external_id(conn, TRUTH_SOCIAL, "loud") is not None
        assert await conn.fetchval("SELECT notified_at FROM posts WHERE id = $1", post_id)


async def test_a_post_under_the_threshold_is_not_announced(pool) -> None:
    await _post(pool, "quiet", score=3)
    gateway = RecordingGateway()

    assert await _alerts(pool, gateway).run(SINCE) == 0
    assert gateway.sent == []


async def test_a_post_no_model_has_read_is_not_announced(pool) -> None:
    """An absent score is not a low one. Announcing it "just in case" would turn the threshold
    into its opposite in the state this module knows least about."""
    await _post(pool, "unread", score=None)
    gateway = RecordingGateway()

    assert await _alerts(pool, gateway).run(SINCE) == 0
    assert gateway.sent == []


@pytest.mark.parametrize(
    "failure",
    [GatewayRefused("the gateway refused: rate limited, 42s"), GatewayUnreachable("no answer")],
    ids=["refused", "unreachable"],
)
async def test_a_failed_delivery_leaves_no_marker_and_the_next_pass_retries(
    pool, failure: Exception
) -> None:
    post_id = await _post(pool, "loud", score=9)
    failing = RecordingGateway(fails=failure)

    assert await _alerts(pool, failing).run(SINCE) == 0
    async with pool.acquire() as conn:
        assert await conn.fetchval("SELECT notified_at FROM posts WHERE id = $1", post_id) is None

    working = RecordingGateway()
    assert await _alerts(pool, working).run(SINCE) == 1
    assert len(working.sent) == 1


async def test_one_post_failing_does_not_stop_the_rest(pool) -> None:
    await _post(pool, "first", score=9)
    await _post(pool, "second", score=10)

    class FailsTheFirst(RecordingGateway):
        async def send(self, *, destination: str, text: str) -> None:
            self.sent.append((destination, text))
            if len(self.sent) == 1:
                raise GatewayUnreachable("no answer")

    gateway = FailsTheFirst()
    assert await _alerts(pool, gateway).run(SINCE) == 1
    assert len(gateway.sent) == 2


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
            translated_model="gpt-5.6-luna",
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
    def test_no_gateway_configured_is_a_supported_state(self, pool, settings) -> None:
        assert alerts.build(pool, settings) is None

    async def test_collection_is_untouched_where_there_is_no_gateway(self, pool) -> None:
        """The rollback lever, and a supported state rather than a fault: clear the address, and the
        archive collects exactly as it did and says nothing."""
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

    def test_a_configured_gateway_is_built(self, pool, settings) -> None:
        configured = settings.model_copy(
            update={
                "telegram_gateway_url": "http://127.0.0.1:8100",
                "alert_destination": "operator",
            }
        )
        assert alerts.build(pool, configured) is not None


class TestConfiguration:
    """Each partial form of the gateway settings is silence that reads like a working
    configuration, which is why every one of them is a refusal to start."""

    def _settings(self, settings, **overrides):
        from social_data.config import Settings

        return Settings(
            **{
                **settings.model_dump(),
                **overrides,
            },
            _env_file=None,
        )

    def test_a_destination_with_no_gateway_is_refused(self, settings) -> None:
        with pytest.raises(ValueError) as err:
            self._settings(settings, alert_destination="operator")
        assert "TELEGRAM_GATEWAY_URL" in str(err.value)

    def test_a_gateway_with_no_destination_is_refused(self, settings) -> None:
        with pytest.raises(ValueError) as err:
            self._settings(settings, telegram_gateway_url="http://127.0.0.1:8100")
        assert "ALERT_DESTINATION" in str(err.value)

    def test_a_gateway_off_this_machine_without_a_scope_is_refused(self, settings) -> None:
        with pytest.raises(ValueError) as err:
            self._settings(
                settings,
                telegram_gateway_url="https://gateway.example.com",
                alert_destination="operator",
            )
        assert "TELEGRAM_GATEWAY_SCOPE" in str(err.value)

    def test_a_threshold_outside_the_reading_range_is_refused(self, settings) -> None:
        with pytest.raises(ValueError) as err:
            self._settings(settings, alert_min_impact_score=11)
        assert "ALERT_MIN_IMPACT_SCORE" in str(err.value)
