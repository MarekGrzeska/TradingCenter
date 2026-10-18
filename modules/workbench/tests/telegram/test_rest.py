"""The REST contract, over the wire it actually answers on.

Every rule these touch is tested at its own layer already — what is asserted here is that the state
reaches the wire: the refusal keeps Telegram's wait, the read keeps no token, and the routes that
manage bots are HTTP routes rather than a shape somebody described.
"""

from __future__ import annotations

import httpx
import pytest

from telegram_gateway.bot_api import Delivered
from telegram_gateway.errors import RateLimited

from . import builders
from .fakes import FakeBotApi, RecordingWatcher

pytestmark = pytest.mark.db


@pytest.fixture
async def api(app, pool, settings):
    """The application with everything its lifespan would have put on it, minus the network."""
    app.state.settings = settings
    app.state.pool = pool
    app.state.telegram = FakeBotApi()
    app.state.watcher = RecordingWatcher()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://tests") as client:
        yield client


class TestSending:
    async def test_a_message_answers_with_the_identifier_telegram_gave_it(
        self, api, app, db
    ) -> None:
        bot = await builders.bot(db)
        destination = await builders.destination(db, name="operator", bot_id=bot.id)
        await db.execute(
            "UPDATE destinations SET chat_id = 5, state = 'ready', bound_at = now() WHERE id = $1",
            destination.id,
        )
        app.state.telegram = FakeBotApi(send=Delivered(message_id=77, chat_id=5))

        response = await api.post("/messages", json={"recipient": "operator", "text": "hi"})

        assert response.status_code == 200
        assert response.json() == {
            "recipient": "operator",
            "message_id": 77,
            "chat_id": 5,
        }

    async def test_a_rate_limit_reaches_the_caller_with_the_wait_telegram_asked_for(
        self, api, app, db
    ) -> None:
        """The caller decides from this whether to record its own "already told" marker, so the
        number has to survive the trip out — a generic 502 would lose the notification."""
        bot = await builders.bot(db)
        destination = await builders.destination(db, name="operator", bot_id=bot.id)
        await db.execute(
            "UPDATE destinations SET chat_id = 5, state = 'ready', bound_at = now() WHERE id = $1",
            destination.id,
        )
        app.state.telegram = FakeBotApi(send=RateLimited(retry_after_seconds=42))

        response = await api.post("/messages", json={"recipient": "operator", "text": "hi"})

        assert response.status_code == 429
        problem = response.json()["detail"]
        assert problem["retry_after_seconds"] == 42
        assert problem["retryable"] is True

    async def test_an_unknown_name_is_refused_and_nothing_is_sent(self, api, app) -> None:
        response = await api.post("/messages", json={"recipient": "nobody", "text": "hi"})

        assert response.status_code == 404
        assert "nobody" in response.json()["detail"]["detail"]
        assert app.state.telegram.sent == []


class TestBots:
    async def test_reading_the_bots_carries_no_token(self, api, db) -> None:
        """The rule with a silent miss: a token in a response looks like a working feature."""
        bot = await builders.bot(db, username="alertsbot")

        response = await api.get("/bots")

        assert response.status_code == 200
        assert [one["username"] for one in response.json()] == ["alertsbot"]
        assert builders.token_for(bot.telegram_id) not in response.text
        assert "token" not in response.text

    async def test_a_pasted_token_becomes_a_bot_telegram_named_itself(self, api, app) -> None:
        app.state.telegram = FakeBotApi(
            me={"id": 4242, "username": "pastedbot", "first_name": "Pasted"}
        )

        response = await api.post("/bots/adopted", json={"token": "4242:" + "B" * 35})

        assert response.status_code == 201
        assert response.json()["username"] == "pastedbot"
        assert response.json()["created_here"] is False
        # Watched from now rather than from the next restart — binding a destination needs a poll.
        assert app.state.watcher.watching == ["pastedbot"]

    async def test_creating_one_with_no_account_logged_in_says_so(self, api) -> None:
        response = await api.post("/bots/created", json={"title": "Alerts", "username": "abot"})

        assert response.status_code == 501
        assert "logged in" in response.json()["detail"]["detail"]

    async def test_deleting_a_bot_this_gateway_does_not_hold_is_a_refusal_about_the_name(
        self, api
    ) -> None:
        response = await api.delete("/bots/nosuchbot")

        assert response.status_code == 404
        assert "nosuchbot" in response.json()["detail"]["detail"]


class TestRecipients:
    async def test_adding_a_bot_to_a_recipient_answers_with_a_link_to_tap(self, api, db) -> None:
        bot = await builders.bot(db, username="alertsbot")
        await api.post("/recipients", json={"name": "operator"})

        response = await api.post("/recipients/operator/bots", json={"bot": "alertsbot"})

        assert response.status_code == 201
        body = response.json()
        assert body["destination"]["state"] == "pending"
        assert body["destination"]["receives"] is False
        assert body["start_link"].startswith(f"https://t.me/{bot.username}?start=")
        assert body["expires_in_seconds"] > 0

    async def test_a_bot_this_gateway_does_not_hold_and_a_recipient_nobody_named_are_refused(self, api, db) -> None:
        await builders.bot(db, username="alertsbot")
        await api.post("/recipients", json={"name": "operator"})

        assert (await api.post("/recipients/operator/bots", json={"bot": "nosuchbot"})).status_code == 404
        assert (await api.post("/recipients/nobody/bots", json={"bot": "alertsbot"})).status_code == 404

    async def test_the_same_recipient_can_be_reached_through_two_bots_each_with_its_own_state(self, api, db) -> None:
        await builders.bot(db, username="postsbot")
        await builders.bot(db, username="filmsbot")
        await api.post("/recipients", json={"name": "operator"})

        await api.post("/recipients/operator/bots", json={"bot": "postsbot"})
        await api.post("/recipients/operator/bots", json={"bot": "filmsbot"})
        await api.post("/recipients/operator/bots", json={"bot": "filmsbot"})  # asked twice: still one binding

        (operator,) = (await api.get("/recipients")).json()
        assert sorted(one["bot"] for one in operator["bindings"]) == ["filmsbot", "postsbot"]
        assert {one["state"] for one in operator["bindings"]} == {"pending"}

    async def test_removing_one_binding_leaves_the_bot_the_recipient_and_its_other_binding(self, api, db) -> None:
        first = await builders.bot(db, username="postsbot")
        second = await builders.bot(db, username="filmsbot")
        await builders.destination(db, name="operator", bot_id=first.id)
        await builders.destination(db, name="operator", bot_id=second.id)

        removed = await api.delete("/recipients/operator/bots/postsbot")

        assert removed.status_code == 204
        (operator,) = (await api.get("/recipients")).json()
        assert [one["bot"] for one in operator["bindings"]] == ["filmsbot"]
        assert sorted(one["username"] for one in (await api.get("/bots")).json()) == ["filmsbot", "postsbot"]

    async def test_removing_a_recipient_takes_every_binding_and_leaves_the_bots(self, api, db) -> None:
        bot = await builders.bot(db, username="alertsbot")
        await builders.destination(db, name="operator", bot_id=bot.id)
        await builders.destination(db, name="risk", bot_id=bot.id)

        removed = await api.delete("/recipients/operator")

        assert removed.status_code == 204
        assert [one["name"] for one in (await api.get("/recipients")).json()] == ["risk"]
        assert [one["username"] for one in (await api.get("/bots")).json()] == ["alertsbot"]

    async def test_a_message_goes_through_the_named_bot_and_is_refused_when_it_would_have_to_guess(
        self, api, app, db
    ) -> None:
        first = await builders.bot(db, username="postsbot")
        second = await builders.bot(db, username="filmsbot")
        for bot in (first, second):
            made = await builders.destination(db, name="operator", bot_id=bot.id)
            await db.execute("UPDATE destinations SET chat_id = 5, state = 'ready' WHERE id = $1", made.id)
        app.state.telegram = FakeBotApi(send=Delivered(message_id=1, chat_id=5))

        guessing = await api.post("/messages", json={"recipient": "operator", "text": "hi"})
        named = await api.post("/messages", json={"recipient": "operator", "bot": "filmsbot", "text": "hi"})
        stranger = await api.post("/messages", json={"recipient": "operator", "bot": "otherbot", "text": "hi"})

        assert guessing.status_code == 409
        assert "postsbot" in guessing.text and "filmsbot" in guessing.text
        assert named.status_code == 200
        assert stranger.status_code == 404
        assert len(app.state.telegram.sent) == 1

    async def test_a_recipient_with_no_bot_yet_cannot_be_written_to(self, api, app) -> None:
        await api.post("/recipients", json={"name": "operator"})

        refused = await api.post("/messages", json={"recipient": "operator", "text": "hi"})

        assert refused.status_code == 404
        assert "not bound through any bot" in refused.text

    async def test_blocking_one_bot_leaves_the_same_recipient_reachable_through_another(self, api, app, db) -> None:
        first = await builders.bot(db, username="postsbot")
        second = await builders.bot(db, username="filmsbot")
        for bot in (first, second):
            made = await builders.destination(db, name="operator", bot_id=bot.id)
            await db.execute("UPDATE destinations SET chat_id = 5, state = 'ready' WHERE id = $1", made.id)
        await db.execute("UPDATE destinations SET state = 'blocked' WHERE bot_id = $1", first.id)
        app.state.telegram = FakeBotApi(send=Delivered(message_id=2, chat_id=5))

        through_blocked = await api.post("/messages", json={"recipient": "operator", "bot": "postsbot", "text": "hi"})
        through_other = await api.post("/messages", json={"recipient": "operator", "bot": "filmsbot", "text": "hi"})

        assert (through_blocked.status_code, through_other.status_code) == (409, 200)


class TestState:
    async def test_a_gateway_with_nothing_in_it_says_so_rather_than_failing(self, api) -> None:
        """A gateway with no destination and a broken one refuse every send alike; only this
        route tells them apart from outside."""
        response = await api.get("/state")

        assert response.status_code == 200
        assert response.json() == {
            "account": {
                "status": "logged_out",
                "username": None,
                "phone": None,
                "reason": None,
                "session_key_configured": False,
                "api_credentials_configured": False,
            },
            "can_create_bots": False,
            "bots": 0,
            "destinations": 0,
            "destinations_ready": 0,
        }

    async def test_it_counts_the_bots_it_holds(self, api, db) -> None:
        await builders.bot(db)

        body = (await api.get("/state")).json()

        assert body["bots"] == 1


class TestAMessageStillAddressedByPurpose:
    async def test_a_request_that_sends_a_purpose_is_refused_and_sends_nothing(self, api, app) -> None:
        """Who is told what is a rule of the alerts package now; a producer that still sends under a purpose hears no, in
        words, rather than being sent to nobody."""
        refused = await api.post("/messages", json={"recipient": "operator", "purpose": "youtube.film", "text": "hi"})

        assert refused.status_code == 422
        assert app.state.telegram.sent == []


async def test_a_destination_goes_with_the_assignments_nothing_reads_any_more(db) -> None:
    """The old tables stay until the conversion is known to have run; until then they must not stop a destination going."""
    destination = await builders.destination(db)
    await db.execute("INSERT INTO assignments (key, destination_id) VALUES ('youtube.film', $1)", destination.id)

    await db.execute("DELETE FROM destinations WHERE id = $1", destination.id)

    assert await db.fetchval("SELECT count(*) FROM assignments") == 0
