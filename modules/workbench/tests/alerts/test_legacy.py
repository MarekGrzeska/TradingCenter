"""What the operator had set, said as rules. The plan is pure and the conversion is a transaction; both are tested for what
an operator would notice if they were wrong — that the people who were told are still told, about the same things, and that
it happens once."""

from __future__ import annotations

import httpx
import pytest

from alerts import conversion, legacy, store
from alerts.contract import EventSource
from alerts.legacy import (
    PLACEHOLDER_TYPES,
    Legacy,
    WatchedChannel,
    WatchedTopic,
    plan,
    recipient_of,
)
from alerts.validation import validate

from .builders import known


def channel(title: str, rule: str = "threshold", active: bool = True) -> WatchedChannel:
    return WatchedChannel(title, rule, active)


def terms_of(rule) -> dict[str, tuple[str, object]]:
    assert isinstance(rule.source, EventSource)
    return {term.attribute: (term.op, term.value) for term in rule.source.filter}


def every_rule_can_stand(rules) -> bool:
    """The rules a conversion makes pass the validation of a rule typed into the form, against the types it stands them on."""
    placeholders = known(
        event_types={name: schema for name, (_, schema) in PLACEHOLDER_TYPES.items()},
        destinations=frozenset({"phone", "tablet"}),
    )
    return all(validate(rule, placeholders) == [] for rule in rules)


def test_the_longest_prefix_decides_and_star_is_last() -> None:
    assignments = {"*": "everyone", "youtube": "a", "youtube.film": "b", "youtube.film.some-channel": "c"}

    assert recipient_of("youtube.film.some-channel", assignments) == "c"
    assert recipient_of("youtube.film.other", assignments) == "b"
    assert recipient_of("social.post.x", assignments) == "everyone"
    assert recipient_of("social.post.x", {"youtube": "a"}) is None


def test_channels_that_told_the_same_person_in_the_same_way_become_one_rule() -> None:
    old = Legacy(
        assignments={"youtube.film": "phone"},
        channels=[channel("Alpha"), channel("Beta"), channel("Gamma", "always"), channel("Delta", "never"), channel("Epsilon", active=False)],
    )

    rules = plan(old)

    assert len(rules) == 2
    threshold = next(rule for rule in rules if "channel" in terms_of(rule) and "impact_score" in terms_of(rule))
    assert terms_of(threshold) == {"channel": ("in", ["Alpha", "Beta"]), "impact_score": ("gte", 8)}
    always = next(rule for rule in rules if "impact_score" not in terms_of(rule))
    assert terms_of(always) == {"channel": ("in", ["Gamma"])}
    assert every_rule_can_stand(rules)


def test_a_channel_with_an_assignment_of_its_own_tells_that_recipient_not_the_general_one() -> None:
    old = Legacy(
        assignments={"youtube.film": "phone", f"youtube.film.{legacy.slug('Beta Channel')}": "tablet"},
        channels=[channel("Alpha"), channel("Beta Channel")],
    )

    rules = plan(old)

    assert {(rule.destination, tuple(terms_of(rule)["channel"][1])) for rule in rules} == {("phone", ("Alpha",)), ("tablet", ("Beta Channel",))}  # pyright: ignore[reportArgumentType]


def test_a_channel_nobody_was_told_about_makes_no_rule() -> None:
    assert plan(Legacy(assignments={}, channels=[channel("Alpha")])) == []
    assert plan(Legacy(assignments={"social": "phone"}, channels=[channel("Alpha")])) == []


def test_topics_tell_whoever_heard_films_in_general() -> None:
    old = Legacy(assignments={"youtube": "phone"}, channels=[], topics=[WatchedTopic("gold", "always", True), WatchedTopic("oil", "never", True)])

    (rule,) = plan(old)

    assert (rule.destination, terms_of(rule)) == ("phone", {"topic": ("in", ["gold"])})


def test_a_threshold_changed_in_the_settings_is_the_threshold_of_the_rule() -> None:
    (rule,) = plan(Legacy(assignments={"*": "phone"}, channels=[channel("Alpha")], youtube_min_score=6))

    assert terms_of(rule)["impact_score"] == ("gte", 6)


def test_posts_go_to_the_author_who_had_a_key_and_everyone_else_to_the_general_recipient() -> None:
    old = Legacy(assignments={"*": "phone", "social.post.alice": "tablet"}, social_min_score=7)

    rules = {rule.destination: rule for rule in plan(old)}

    assert terms_of(rules["tablet"]) == {"author_slug": ("eq", "alice"), "impact_score": ("gte", 7)}
    assert terms_of(rules["phone"]) == {"impact_score": ("gte", 7), "author_slug": ("ne", "alice")}
    assert every_rule_can_stand(rules.values())


def test_without_the_post_archive_or_the_youtube_archive_there_is_nothing_to_convert_for_it() -> None:
    assert plan(Legacy(assignments={"*": "phone"}, channels=None, social_min_score=None)) == []


@pytest.mark.db
class TestConversion:
    class Source:
        def __init__(self, old: Legacy | None) -> None:
            self.old = old
            self.asked = 0

        async def read(self) -> Legacy | None:
            self.asked += 1
            return self.old

    OLD = Legacy(assignments={"*": "phone"}, channels=[channel("Alpha")], social_min_score=8)

    async def test_the_old_settings_become_rules_once(self, pool, db) -> None:
        source = self.Source(self.OLD)

        first = await conversion.run(pool, source)
        again = await conversion.run(pool, source)

        assert (first, again) == (2, 0)
        assert await db.fetchval("SELECT count(*) FROM rules WHERE created_by = 'conversion'") == 2
        assert source.asked == 1, "once it is done the neighbours are not asked again"

    async def test_neighbours_that_cannot_answer_yet_leave_no_marker_and_no_rules(self, pool, db) -> None:
        assert await conversion.run(pool, self.Source(None)) is None

        assert await db.fetchval("SELECT count(*) FROM migrations_done") == 0
        assert await conversion.run(pool, self.Source(self.OLD)) == 2

    async def test_it_waits_for_the_neighbours_and_converts_when_they_answer(self, pool, db) -> None:
        source = self.Source(None)

        async def answer_later():
            import asyncio

            await asyncio.sleep(0.05)
            source.old = self.OLD

        import asyncio

        later = asyncio.create_task(answer_later())
        made = await conversion.run_when_ready(pool, source, pause=0.02)
        await later

        assert made == 2

    async def test_a_type_a_producer_already_announced_is_not_replaced_by_the_placeholder(self, pool, db) -> None:
        async with pool.acquire() as conn:
            await store.upsert_event_type(conn, legacy.YOUTUBE_FILM, description="the real one", schema={"type": "object"}, announced_by="youtube")

        await conversion.run(pool, self.Source(self.OLD))

        assert await db.fetchval("SELECT description FROM event_types WHERE name = $1", legacy.YOUTUBE_FILM) == "the real one"

    async def test_nothing_set_is_also_an_answer_and_is_not_asked_twice(self, pool, db) -> None:
        source = self.Source(Legacy())

        assert await conversion.run(pool, source) == 0
        assert await conversion.run(pool, source) == 0
        assert source.asked == 1

    async def test_no_source_at_all_converts_nothing(self, pool, db) -> None:
        assert await conversion.run(pool, None) == 0


async def test_the_assembly_reads_the_neighbours_in_the_shapes_they_publish() -> None:
    from workbench.legacy_alerts import LegacyAlerts

    def answer(request: httpx.Request) -> httpx.Response:
        body = {
            "/assignments": [{"key": "*", "destination": "phone", "bot": "@b", "receives": True}],
            "/channels": {"channels": [{"title": "Alpha", "alert_rule": "always", "active": True}], "ceiling": 100},
            "/topics": {"topics": [{"phrase": "gold", "alert_rule": "threshold", "active": False}], "ceiling": 20},
        }[request.url.path]
        return httpx.Response(200, json=body)

    def client(handler) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://x")

    reader = LegacyAlerts(client(answer), client(answer), youtube_min_score=9, social_min_score=7)
    old = await reader.read()

    assert old is not None
    assert old.assignments == {"*": "phone"}
    assert old.channels == [WatchedChannel("Alpha", "always", True)]
    assert old.topics == [WatchedTopic("gold", "threshold", False)]
    assert (old.youtube_min_score, old.social_min_score) == (9, 7)

    starting = LegacyAlerts(client(lambda request: httpx.Response(500)), None, youtube_min_score=8, social_min_score=8)
    assert await starting.read() is None
