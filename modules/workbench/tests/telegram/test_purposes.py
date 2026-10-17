"""Purposes: the shape of one, which assignment hears it, and what reaches the wire. The matching rule is
tested once, as a function; the database tests prove the statement agrees with it, and the REST ones that
the state reaches the wire."""

from __future__ import annotations

import asyncpg
import httpx
import pytest

from telegram_gateway import purposes, sending, store
from telegram_gateway.errors import (
    InvalidPurpose,
    PurposeUnassigned,
    StillAssigned,
)

from . import builders
from .fakes import FakeBotApi, RecordingWatcher
from .test_sending import ready_destination

CEILING = 4096


class TestTheShapeOfAPurpose:
    @pytest.mark.parametrize("name", ["youtube", "youtube.film", "market.price.eurusd", "a-b_c.d9"])
    def test_a_dotted_lowercase_name_is_a_purpose(self, name: str) -> None:
        assert purposes.valid_purpose(name) == name

    @pytest.mark.parametrize(
        "name", ["", "YouTube", "a..b", ".a", "a.", "a b", "a." + "x" * 130, "*"]
    )
    def test_anything_else_is_refused_naming_the_shape(self, name: str) -> None:
        with pytest.raises(InvalidPurpose, match="lowercase"):
            purposes.valid_purpose(name)

    def test_only_a_key_may_be_the_default(self) -> None:
        assert purposes.valid_key("*") == "*"


class TestWhichKeyDecides:
    def test_the_candidates_run_from_the_purpose_to_the_default(self) -> None:
        assert purposes.candidates("youtube.film.chan") == [
            "youtube.film.chan",
            "youtube.film",
            "youtube",
            "*",
        ]

    def test_the_most_specific_present_key_wins(self) -> None:
        keys = {"youtube", "youtube.film", "*"}
        assert purposes.deciding_key("youtube.film.chan", keys) == "youtube.film"
        assert purposes.deciding_key("youtube.live", keys) == "youtube"
        assert purposes.deciding_key("social.post", keys) == "*"

    def test_a_prefix_does_not_cut_a_segment(self) -> None:
        assert purposes.deciding_key("market.prices", {"market.price"}) is None

    def test_nothing_decides_without_a_default(self) -> None:
        assert purposes.deciding_key("social.post", {"youtube"}) is None


@pytest.mark.db
class TestTheStatementAgreesWithTheRule:
    async def test_the_recipient_is_the_one_the_rule_names(self, db) -> None:
        bot = await builders.bot(db)
        broad = await builders.destination(db, name="broad", bot_id=bot.id)
        narrow = await builders.destination(db, name="narrow", bot_id=bot.id)
        fallback = await builders.destination(db, name="fallback", bot_id=bot.id)
        await store.assign(db, key="youtube", destination_id=broad.id)
        await store.assign(db, key="youtube.film.chan", destination_id=narrow.id)
        await store.assign(db, key="*", destination_id=fallback.id)

        async def hears(purpose: str) -> str | None:
            one = await store.recipient_of(db, purpose)
            return one.name if one else None

        assert await hears("youtube.film.chan") == "narrow"
        assert await hears("youtube.film.other") == "broad"
        assert await hears("social.post") == "fallback"

    async def test_without_a_default_an_unmatched_purpose_has_no_recipient(self, db) -> None:
        one = await builders.destination(db, name="one")
        await store.assign(db, key="youtube", destination_id=one.id)

        assert await store.recipient_of(db, "social.post") is None

    async def test_assigning_a_key_again_moves_it(self, db) -> None:
        bot = await builders.bot(db)
        first = await builders.destination(db, name="first", bot_id=bot.id)
        second = await builders.destination(db, name="second", bot_id=bot.id)
        await store.assign(db, key="*", destination_id=first.id)
        await store.assign(db, key="*", destination_id=second.id)

        [(assignment, destination)] = await store.list_assignments(db)

        assert (assignment.key, destination.name) == ("*", "second")


@pytest.mark.db
class TestSendingByPurpose:
    async def test_the_message_goes_to_whoever_hears_it(self, db) -> None:
        destination = await ready_destination(db, "operator")
        assert destination is not None
        await store.assign(db, key="youtube", destination_id=destination.id)
        api = FakeBotApi()

        reached, delivered = await sending.send_to_purpose(
            db,
            api,
            purpose="youtube.film.chan",
            text="new film",
            max_chars=CEILING,
            caller="the YouTube archive",
        )

        assert reached.name == "operator"
        assert api.sent[0][1:] == (delivered.chat_id, "new film")

    async def test_a_purpose_nobody_hears_is_noted_and_refused_apart_from_every_other_refusal(
        self, db
    ) -> None:
        api = FakeBotApi()

        with pytest.raises(PurposeUnassigned, match="social.post"):
            await sending.send_to_purpose(
                db,
                api,
                purpose="social.post.x",
                text="hi",
                max_chars=CEILING,
                caller="the post archive",
            )

        assert api.sent == []
        [seen] = await store.list_purposes(db)
        assert (seen.name, seen.last_caller) == ("social.post.x", "the post archive")
        assert await store.count_unheard(db) == 1

    async def test_a_default_assignment_hears_what_nobody_named(self, db) -> None:
        destination = await ready_destination(db, "operator")
        assert destination is not None
        await store.assign(db, key="*", destination_id=destination.id)

        await sending.send_to_purpose(
            db, FakeBotApi(), purpose="anything.at.all", text="hi", max_chars=CEILING, caller=None
        )

        assert await store.count_unheard(db) == 0

    async def test_the_message_text_is_never_kept(self, db) -> None:
        destination = await ready_destination(db, "operator")
        assert destination is not None
        await store.assign(db, key="*", destination_id=destination.id)

        await sending.send_to_purpose(
            db, FakeBotApi(), purpose="a.b", text="SECRET-TEXT", max_chars=CEILING, caller=None
        )

        rows = await db.fetch("SELECT * FROM purposes")
        assert "SECRET-TEXT" not in str([dict(row) for row in rows])


@pytest.mark.db
class TestRemovingWhatIsStillHeard:
    async def test_the_schema_holds_when_a_route_forgets(self, db) -> None:
        one = await builders.destination(db, name="one")
        await store.assign(db, key="*", destination_id=one.id)

        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await store.remove_destination(db, "one")

    async def test_the_keys_are_named_for_a_destination_and_for_its_bot(self, db) -> None:
        bot = await builders.bot(db)
        one = await builders.destination(db, name="one", bot_id=bot.id)
        await store.assign(db, key="youtube", destination_id=one.id)
        await store.assign(db, key="*", destination_id=one.id)

        assert await store.assigned_to(db, one.id) == ["*", "youtube"]
        assert await store.assigned_to_bot(db, bot.id) == ["*", "youtube"]
        assert "'*'" in str(StillAssigned(what="'one'", keys=["*", "youtube"]))


@pytest.fixture
async def api(app, pool, settings):
    app.state.settings = settings
    app.state.pool = pool
    app.state.telegram = FakeBotApi()
    app.state.watcher = RecordingWatcher()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://tests") as client:
        yield client


@pytest.mark.db
class TestOnTheWire:
    async def test_an_unheard_purpose_answers_409_with_its_own_code(self, api) -> None:
        response = await api.post("/messages", json={"purpose": "social.post", "text": "hi"})

        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "unassigned"

    async def test_a_purpose_reaches_the_wire_and_names_where_it_went(self, api, db) -> None:
        destination = await ready_destination(db, "operator")
        assert destination is not None
        await store.assign(db, key="*", destination_id=destination.id)

        response = await api.post("/messages", json={"purpose": "social.post", "text": "hi"})

        assert response.status_code == 200
        assert response.json()["destination"] == "operator"
        assert response.json()["purpose"] == "social.post"

    @pytest.mark.parametrize(
        "body",
        [
            {"text": "hi"},
            {"destination": "a", "purpose": "b", "text": "hi"},
            {"purpose": "No", "text": "hi"},
        ],
    )
    async def test_exactly_one_address_in_a_valid_shape(self, api, body) -> None:
        response = await api.post("/messages", json=body)

        assert response.status_code == 422

    async def test_assigning_lists_and_listing_shows_who_decides(self, api, db) -> None:
        destination = await ready_destination(db, "operator")
        assert destination is not None
        await api.post("/messages", json={"purpose": "youtube.film.chan", "text": "hi"})

        assigned = await api.put("/assignments/youtube", json={"destination": "operator"})
        listed = (await api.get("/purposes")).json()

        assert assigned.status_code == 200
        assert [(p["name"], p["destination"], p["assigned_by"]) for p in listed] == [
            ("youtube.film.chan", "operator", "youtube")
        ]
        assert (await api.get("/state")).json()["purposes_unheard"] == 0

    async def test_a_destination_that_is_heard_cannot_be_removed_and_the_refusal_names_the_key(
        self, api, db
    ) -> None:
        destination = await ready_destination(db, "operator")
        assert destination is not None
        await api.put("/assignments/*", json={"destination": "operator"})

        response = await api.delete("/destinations/operator")

        assert response.status_code == 409
        assert "'*'" in response.json()["detail"]["detail"]

    async def test_a_bot_with_a_heard_destination_is_refused_before_the_creator_bot_is_asked(
        self, api, db
    ) -> None:
        destination = await ready_destination(db, "operator")
        assert destination is not None
        bot = await store.bot_by_id(db, destination.bot_id)
        assert bot is not None
        await api.put("/assignments/youtube", json={"destination": "operator"})

        response = await api.delete(f"/bots/{bot.username}")

        assert response.status_code == 409
        assert "'youtube'" in response.json()["detail"]["detail"]

    async def test_an_announced_purpose_is_listed_before_any_event(self, api) -> None:
        await api.put(
            "/purposes/market.price.eurusd", json={"description": "price alert on EURUSD"}
        )

        [one] = (await api.get("/purposes")).json()

        assert (one["name"], one["description"], one["destination"]) == (
            "market.price.eurusd",
            "price alert on EURUSD",
            None,
        )


@pytest.mark.db
class TestSeedingFromTheRetiredSetting:
    async def test_the_retired_setting_becomes_the_default_once_and_never_overwrites(self, db) -> None:
        from telegram_gateway.app import seed_default_assignment

        bot = await builders.bot(db)
        old = await builders.destination(db, name="old", bot_id=bot.id)
        await builders.destination(db, name="chosen", bot_id=bot.id)

        await seed_default_assignment(db, "old")
        await seed_default_assignment(db, "chosen")

        [(assignment, destination)] = await store.list_assignments(db)
        assert (assignment.key, destination.id) == ("*", old.id)

    async def test_a_name_that_is_no_destination_seeds_nothing(self, db) -> None:
        from telegram_gateway.app import seed_default_assignment

        await seed_default_assignment(db, "nobody")

        assert await store.list_assignments(db) == []
