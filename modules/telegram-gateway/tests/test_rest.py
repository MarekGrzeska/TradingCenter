"""The REST contract, over the wire it actually answers on.

Every rule these touch is tested at its own layer already — what is asserted here is that the state
reaches the wire: the refusal keeps Telegram's wait, the read keeps no token, and the routes that
manage bots are HTTP routes rather than a shape somebody described.
"""

from __future__ import annotations

import builders
import httpx
import pytest
from fakes import FakeBotApi, RecordingWatcher

from telegram_gateway.bot_api import Delivered
from telegram_gateway.config import Settings
from telegram_gateway.errors import RateLimited

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

        response = await api.post("/messages", json={"destination": "operator", "text": "hi"})

        assert response.status_code == 200
        assert response.json() == {"destination": "operator", "message_id": 77, "chat_id": 5}

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

        response = await api.post("/messages", json={"destination": "operator", "text": "hi"})

        assert response.status_code == 429
        problem = response.json()["detail"]
        assert problem["retry_after_seconds"] == 42
        assert problem["retryable"] is True

    async def test_an_unknown_name_is_refused_and_nothing_is_sent(self, api, app) -> None:
        response = await api.post("/messages", json={"destination": "nobody", "text": "hi"})

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

    async def test_creating_one_without_an_account_session_names_the_missing_setting(
        self, api
    ) -> None:
        response = await api.post("/bots/created", json={"title": "Alerts", "username": "abot"})

        assert response.status_code == 501
        assert "TELEGRAM_SESSION" in response.json()["detail"]["detail"]

    async def test_deleting_a_bot_this_gateway_does_not_hold_is_a_refusal_about_the_name(
        self, api
    ) -> None:
        response = await api.delete("/bots/nosuchbot")

        assert response.status_code == 404
        assert "nosuchbot" in response.json()["detail"]["detail"]


class TestDestinations:
    async def test_asking_for_a_destination_answers_with_a_link_to_tap(self, api, db) -> None:
        bot = await builders.bot(db, username="alertsbot")

        response = await api.post("/destinations", json={"name": "operator", "bot": "alertsbot"})

        assert response.status_code == 201
        body = response.json()
        assert body["destination"]["state"] == "pending"
        assert body["destination"]["receives"] is False
        assert body["start_link"].startswith(f"https://t.me/{bot.username}?start=")
        assert body["expires_in_seconds"] > 0

    async def test_a_bot_this_gateway_does_not_hold_is_refused(self, api) -> None:
        response = await api.post("/destinations", json={"name": "operator", "bot": "nosuchbot"})

        assert response.status_code == 404

    async def test_removing_a_destination_leaves_the_bot_and_its_others_standing(
        self, api, db
    ) -> None:
        bot = await builders.bot(db, username="alertsbot")
        await builders.destination(db, name="operator", bot_id=bot.id)
        await builders.destination(db, name="risk", bot_id=bot.id)

        removed = await api.delete("/destinations/operator")

        assert removed.status_code == 204
        assert [one["name"] for one in (await api.get("/destinations")).json()] == ["risk"]
        assert [one["username"] for one in (await api.get("/bots")).json()] == ["alertsbot"]


class TestState:
    async def test_a_gateway_with_nothing_in_it_says_so_rather_than_failing(self, api) -> None:
        """A gateway with no destination and a broken one refuse every send alike; only this
        route tells them apart from outside."""
        response = await api.get("/state")

        assert response.status_code == 200
        assert response.json() == {
            "account_session_configured": False,
            "bots": 0,
            "destinations": 0,
            "destinations_ready": 0,
        }

    async def test_it_reports_the_account_session_when_there_is_one(self, api, app, db) -> None:
        app.state.settings = Settings(
            database_url="postgresql://localhost:5432/test?sslmode=require",
            database_user="test-user",
            telegram_api_id=1,
            telegram_api_hash="hash",
            telegram_session="session",
            _env_file=None,
        )
        await builders.bot(db)

        body = (await api.get("/state")).json()

        assert body["account_session_configured"] is True
        assert body["bots"] == 1
