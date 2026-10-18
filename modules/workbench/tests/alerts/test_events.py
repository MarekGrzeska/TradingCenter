"""Events: that a filter says what it should (pure), and that an event goes through a database to the rules it satisfies,
once."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from tc_runtime.liveness import LoopHeartbeat

from alerts import filtering, store
from alerts.clock import Clock
from alerts.contract import FilterTerm

from .builders import FILM_SCHEMA, event, rule

CHANNEL = FilterTerm(attribute="channel", op="eq", value="Some channel")
FILM = {"channel": "Some channel", "impact_score": 8, "instruments": ["EURUSD", "XAUUSD"], "forming": False, "text": "x"}


@pytest.mark.parametrize(
    ("term", "attributes", "expected"),
    [
        (CHANNEL, FILM, True),
        (CHANNEL, {**FILM, "channel": "Other"}, False),
        (FilterTerm(attribute="impact_score", op="gte", value=8), FILM, True),
        (FilterTerm(attribute="impact_score", op="gt", value=8), FILM, False),
        (FilterTerm(attribute="impact_score", op="in", value=["7", "8"]), FILM, True),
        (FilterTerm(attribute="channel", op="in", value=["A", "B"]), FILM, False),
        (FilterTerm(attribute="instruments", op="contains", value="XAUUSD"), FILM, True),
        (FilterTerm(attribute="instruments", op="contains", value="GBPUSD"), FILM, False),
        (FilterTerm(attribute="forming", op="eq", value=False), FILM, True),
        (FilterTerm(attribute="channel", op="ne", value="Other"), FILM, True),
        (FilterTerm(attribute="channel", op="eq", value="x"), {}, False),
        (FilterTerm(attribute="channel", op="ne", value="x"), {}, True),
        (FilterTerm(attribute="impact_score", op="gt", value=1), {**FILM, "impact_score": "high"}, False),
    ],
)
def test_a_term_holds_for_an_event_that_has_what_it_asks(term, attributes, expected) -> None:
    assert filtering.matches([term], attributes) is expected


def test_every_term_has_to_hold_and_no_terms_asks_for_everything() -> None:
    high = FilterTerm(attribute="impact_score", op="gte", value=9)

    assert filtering.matches([CHANNEL, high], FILM) is False
    assert filtering.matches([], {}) is True


@pytest.mark.db
class TestPublishing:
    @pytest.fixture(autouse=True)
    async def announced(self, db, inside):
        await inside.put("/event-types/youtube.film.read", json={"description": "a film", "schema": FILM_SCHEMA})

    @staticmethod
    def film(key: str = "film-1", **attributes) -> dict:
        return {"type": "youtube.film.read", "source_key": key, "attributes": {**FILM, **attributes}, "text": "The film, in words"}

    @staticmethod
    async def rule_for(api, terms=None, **overrides) -> int:
        body = rule(event(terms or []), **overrides).model_dump(mode="json")
        response = await api.post("/rules", json=body)
        assert response.status_code == 201, response.text
        return response.json()["id"]

    async def test_an_event_makes_every_rule_that_wants_it_go_off_with_its_own_words(self, api, inside, db) -> None:
        wanted = await self.rule_for(api, [CHANNEL], template="{channel}: {impact_score}")
        await self.rule_for(api, [FilterTerm(attribute="impact_score", op="gte", value=9)])

        accepted = (await inside.post("/events", json=self.film())).json()

        assert (accepted["duplicate"], accepted["fires"]) == (False, 1)
        assert [row["text"] for row in await db.fetch("SELECT text FROM fires WHERE rule_id = $1", wanted)] == ["Some channel: 8"]

    async def test_the_default_message_is_the_one_the_producer_wrote(self, api, inside, db) -> None:
        await self.rule_for(api)

        await inside.post("/events", json=self.film())

        assert await db.fetchval("SELECT text FROM fires") == "The film, in words"

    async def test_the_same_occurrence_published_twice_is_one_yes_and_one_alert(self, api, inside, db) -> None:
        await self.rule_for(api)

        first = (await inside.post("/events", json=self.film())).json()
        second = (await inside.post("/events", json=self.film())).json()

        assert (first["duplicate"], second["duplicate"]) == (False, True)
        assert first["id"] == second["id"]
        assert await db.fetchval("SELECT count(*) FROM fires") == 1

    async def test_an_event_that_does_not_fit_its_type_or_has_none_is_refused(self, api, inside, db) -> None:
        wrong = await inside.post("/events", json=self.film(impact_score="high"))
        nameless = await inside.post("/events", json={**self.film(), "type": "nobody.announced"})

        assert wrong.status_code == 422 and "impact_score" in wrong.json()["detail"]["detail"]
        assert nameless.status_code == 422
        assert await db.fetchval("SELECT count(*) FROM events") == 0

    async def test_nobody_from_outside_can_publish(self, api, db) -> None:
        refused = await api.post("/events", json=self.film())

        assert refused.status_code == 403
        assert await db.fetchval("SELECT count(*) FROM events") == 0

    async def test_a_second_match_inside_the_cooldown_is_a_line_in_the_history_not_a_message(self, api, inside, db) -> None:
        rule_id = await self.rule_for(api, cooldown_seconds=600)

        await inside.post("/events", json=self.film("a"))
        await inside.post("/events", json=self.film("b"))

        assert await db.fetchval("SELECT count(*) FROM fires WHERE rule_id = $1", rule_id) == 1
        assert [row["outcome"] for row in await db.fetch("SELECT outcome FROM rule_checks WHERE rule_id = $1", rule_id)] == ["cooldown"]

    async def test_a_switched_off_rule_and_a_once_rule_already_told_are_left_alone(self, api, inside, db) -> None:
        off = await self.rule_for(api, enabled=False)
        once = await self.rule_for(api, mode="once")

        await inside.post("/events", json=self.film("a"))
        await inside.post("/events", json=self.film("b"))

        assert await db.fetchval("SELECT count(*) FROM fires WHERE rule_id = $1", off) == 0
        assert await db.fetchval("SELECT count(*) FROM fires WHERE rule_id = $1", once) == 1

    async def test_the_clock_forgets_events_after_their_retention_and_keeps_what_they_caused(self, api, inside, db, pool, settings) -> None:
        await self.rule_for(api)
        await inside.post("/events", json=self.film())
        clock = Clock(pool, settings, None, LoopHeartbeat("clock", expected_seconds=5))

        await clock.tick(datetime.now(UTC) + timedelta(days=settings.event_retention_days + 1))

        assert await db.fetchval("SELECT count(*) FROM events") == 0
        assert await db.fetchval("SELECT count(*) FROM fires") == 1
        assert await db.fetchval("SELECT event_id FROM fires") is None


async def test_the_store_says_an_event_published_twice_is_a_duplicate(pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO event_types (name, description, schema) VALUES ('t', 'd', '{}')")
        now = datetime.now(UTC)
        first = await store.insert_event(conn, type_="t", source_key="k", attributes={}, text="x", now=now)
        again = await store.insert_event(conn, type_="t", source_key="k", attributes={}, text="x", now=now)

    assert first[1] is False and again == (first[0], True)
