"""The account that owns the bots: logging it in from the terminal, keeping its session where a dump cannot use it,
and every way it can stop being usable. The rules with a quiet failure get their own tests — a session in plaintext,
a code in a log, an account that stays usable after the operator forgot it."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from telegram_gateway import account, session_crypto, store
from telegram_gateway.account import AccountStatus, LoginManager, mask_phone
from telegram_gateway.config import Settings
from telegram_gateway.errors import (
    CreatingBotsUnavailable,
    LoginNotInProgress,
    LoginRefused,
    SessionRejected,
)

from . import builders, fakes
from .fakes import FakeBotApi, FakeCreatorBot, FakeLoginClient, FakePlatform, RecordingWatcher

KEY = "NPaSFWjv9LBWO9H7PecpB7pmGeKWx4OF1CwOnRUOFA0="
OTHER_KEY = "jLfdYT1y0nZLEf2w_hXQKjHaJrMpv4I6Cq2qVDxVpUc="
PHONE = "+48123456789"


def owner_settings(**overrides) -> Settings:
    base = {
        "database_url": "postgresql://localhost:5432/test?sslmode=require",
        "database_user": "test-user",
        "telegram_api_id": 12345,
        "telegram_api_hash": "hash",
        "telegram_session_key": KEY,
        "_env_file": None,
    }
    return Settings(**{**base, **overrides})


class TestThePhoneNumber:
    def test_only_the_last_four_digits_are_shown(self) -> None:
        assert mask_phone("+48123456789") == "+•••••••6789"

    @pytest.mark.parametrize("phone", ["123456789", "+48", "+48 abc", ""])
    def test_a_number_not_in_international_form_is_refused_before_telegram(self, phone: str) -> None:
        with pytest.raises(LoginRefused, match="international"):
            account.valid_phone(phone)

    def test_spaces_and_dashes_are_forgiven(self) -> None:
        assert account.valid_phone("+48 123-456-789") == "+48123456789"


class TestTheSessionAtRest:
    def test_what_is_stored_is_not_the_session(self) -> None:
        stored = session_crypto.encrypt(KEY, "SESSION-STRING-1")

        assert "SESSION-STRING-1" not in stored
        assert session_crypto.decrypt(KEY, stored) == "SESSION-STRING-1"

    def test_another_key_opens_nothing(self) -> None:
        stored = session_crypto.encrypt(KEY, "SESSION-STRING-1")

        assert session_crypto.decrypt(OTHER_KEY, stored) is None


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


class TestTheLoginInMemory:
    async def test_a_wrong_code_leaves_the_login_open_for_another(self) -> None:
        client = FakeLoginClient(code="12345")
        manager = LoginManager(lambda *_: client)
        await manager.begin(PHONE, api_id=1, api_hash="h")

        with pytest.raises(LoginRefused, match="wrong"):
            await manager.code("00000")
        identity = await manager.code("12345")

        assert identity is not None and identity.username == "ownerbot_account"

    async def test_an_account_with_a_password_asks_for_it_after_the_code(self) -> None:
        client = FakeLoginClient(password="hunter2")
        manager = LoginManager(lambda *_: client)
        await manager.begin(PHONE, api_id=1, api_hash="h")

        assert await manager.code("12345") is None
        identity = await manager.password("hunter2")

        assert identity.session == "SESSION-STRING-1"
        assert client.disconnected is True

    async def test_a_login_expires_after_ten_minutes(self) -> None:
        clock = Clock()
        manager = LoginManager(lambda *_: FakeLoginClient(), clock=clock)
        await manager.begin(PHONE, api_id=1, api_hash="h")
        clock.now += timedelta(minutes=10, seconds=1)

        with pytest.raises(LoginNotInProgress):
            await manager.code("12345")

    async def test_a_code_with_no_login_is_a_refusal_about_the_login(self) -> None:
        with pytest.raises(LoginNotInProgress, match="Start again"):
            await LoginManager(lambda *_: FakeLoginClient()).code("12345")

    async def test_starting_again_replaces_the_login_in_progress(self) -> None:
        first, second = FakeLoginClient(code="11111"), FakeLoginClient(code="22222")
        clients = iter([first, second])
        manager = LoginManager(lambda *_: next(clients))
        await manager.begin(PHONE, api_id=1, api_hash="h")
        await manager.begin(PHONE, api_id=1, api_hash="h")

        assert first.disconnected is True
        assert await manager.code("22222") is not None

    async def test_a_refused_start_leaves_nothing_connected(self) -> None:
        client = FakeLoginClient(send_error=LoginRefused("Telegram does not accept that number"))
        manager = LoginManager(lambda *_: client)

        with pytest.raises(LoginRefused):
            await manager.begin(PHONE, api_id=1, api_hash="h")

        assert client.disconnected is True


@pytest.mark.db
class TestWhatTheStoredAccountCanDo:
    async def test_nothing_stored_is_logged_out(self, db) -> None:
        assert (await account.view(db, owner_settings())).status is AccountStatus.LOGGED_OUT

    async def test_a_login_is_stored_encrypted_and_usable(self, db) -> None:
        settings = owner_settings()
        await account.save_login(
            db, settings, account.Identity("owner", PHONE, "SESSION-STRING-1")
        )

        row = await db.fetchrow("SELECT * FROM account_session")
        assert "SESSION-STRING-1" not in str(dict(row))
        assert PHONE not in str(dict(row))
        assert (await account.view(db, settings)).status is AccountStatus.LOGGED_IN
        assert await account.usable_session(db, settings) == "SESSION-STRING-1"

    async def test_a_changed_key_is_a_state_that_names_the_key(self, db) -> None:
        await account.save_login(db, owner_settings(), account.Identity("owner", PHONE, "S"))

        current = await account.view(db, owner_settings(telegram_session_key=OTHER_KEY))

        assert current.status is AccountStatus.NEEDS_LOGIN
        assert "key" in (current.reason or "")
        with pytest.raises(CreatingBotsUnavailable, match="logging in again"):
            await account.usable_session(db, owner_settings(telegram_session_key=OTHER_KEY))

    async def test_a_session_telegram_refused_is_remembered(self, db) -> None:
        settings = owner_settings()
        await account.save_login(db, settings, account.Identity("owner", PHONE, "S"))

        await store.mark_account_rejected(db)

        assert (await account.view(db, settings)).reason == "Telegram rejected the session"

    async def test_logging_in_again_clears_a_rejection(self, db) -> None:
        settings = owner_settings()
        await account.save_login(db, settings, account.Identity("owner", PHONE, "S"))
        await store.mark_account_rejected(db)

        await account.save_login(db, settings, account.Identity("owner", PHONE, "S2"))

        assert (await account.view(db, settings)).status is AccountStatus.LOGGED_IN


@pytest.fixture
async def platform() -> FakePlatform:
    return FakePlatform()


@pytest.fixture
async def api(app, pool, platform):
    app.state.settings = owner_settings()
    app.state.pool = pool
    app.state.telegram = FakeBotApi()
    app.state.watcher = RecordingWatcher()
    app.state.platform = platform
    app.state.login = LoginManager(platform.login_client)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://tests") as client:
        yield client


async def log_in(api) -> None:
    await api.post("/account/login", json={"phone": PHONE})
    await api.post("/account/login/code", json={"code": "12345"})


@pytest.mark.db
class TestLoggingInOverTheWire:
    async def test_phone_then_code_ends_with_the_account_and_a_masked_number(self, api) -> None:
        started = await api.post("/account/login", json={"phone": PHONE})
        finished = await api.post("/account/login/code", json={"code": "12345"})

        assert started.json() == {"step": "code", "account": None, "delivery": "app", "can_resend": True}
        assert finished.json()["step"] == "done"
        owner = finished.json()["account"]
        assert (owner["status"], owner["username"], owner["phone"]) == (
            "logged_in",
            "ownerbot_account",
            "+•••••••6789",
        )

    async def test_a_code_that_did_not_come_is_asked_for_again_by_another_way_on_the_same_login(
        self, api, platform
    ) -> None:
        await api.post("/account/login", json={"phone": PHONE})

        again = await api.post("/account/login/resend")
        finished = await api.post("/account/login/code", json={"code": "12345"})

        assert again.json() == {"step": "code", "account": None, "delivery": "sms", "can_resend": False}
        assert platform.login.resends == 1
        assert finished.json()["step"] == "done"

    async def test_resending_without_a_login_is_a_refusal_about_the_login(self, api) -> None:
        response = await api.post("/account/login/resend")

        assert response.status_code == 409
        assert "Start again" in response.json()["detail"]["detail"]

    async def test_an_account_with_a_password_walks_one_more_step(self, api, platform) -> None:
        platform.login = FakeLoginClient(password="hunter2")

        await api.post("/account/login", json={"phone": PHONE})
        asked = await api.post("/account/login/code", json={"code": "12345"})
        done = await api.post("/account/login/password", json={"password": "hunter2"})

        assert asked.json()["step"] == "password"
        assert done.json()["step"] == "done"

    async def test_a_wrong_code_is_telegrams_refusal_and_the_login_stays_open(self, api) -> None:
        await api.post("/account/login", json={"phone": PHONE})

        wrong = await api.post("/account/login/code", json={"code": "00000"})
        right = await api.post("/account/login/code", json={"code": "12345"})

        assert wrong.status_code == 409
        assert "wrong" in wrong.json()["detail"]["detail"]
        assert right.json()["step"] == "done"

    async def test_without_the_key_nothing_is_asked_of_telegram(self, api, app, platform) -> None:
        app.state.settings = owner_settings(telegram_session_key=None)

        response = await api.post("/account/login", json={"phone": PHONE})

        assert response.status_code == 501
        assert "TELEGRAM_SESSION_KEY" in response.json()["detail"]["detail"]
        assert platform.login.phone is None

    async def test_without_the_application_credentials_they_are_named(self, api, app) -> None:
        app.state.settings = owner_settings(telegram_api_id=None, telegram_api_hash=None)

        response = await api.post("/account/login", json={"phone": PHONE})

        assert "TELEGRAM_API_ID" in response.json()["detail"]["detail"]

    async def test_the_state_says_whose_account_it_is_and_never_the_session(self, api) -> None:
        await log_in(api)

        state = (await api.get("/state")).json()

        assert state["account"]["username"] == "ownerbot_account"
        assert state["can_create_bots"] is True
        assert "SESSION-STRING-1" not in str(state)

    async def test_neither_the_code_nor_the_password_reaches_a_log(self, api, platform, caplog) -> None:
        platform.login = FakeLoginClient(password="hunter2-secret", code="98765")
        with caplog.at_level(logging.DEBUG):
            await api.post("/account/login", json={"phone": PHONE})
            await api.post("/account/login/code", json={"code": "00000"})
            await api.post("/account/login/code", json={"code": "98765"})
            await api.post("/account/login/password", json={"password": "hunter2-secret"})

        assert "98765" not in caplog.text
        assert "hunter2-secret" not in caplog.text
        assert "SESSION-STRING-1" not in caplog.text


@pytest.mark.db
class TestLoggingOut:
    async def test_the_session_is_ended_at_telegram_and_forgotten_here(self, api, platform) -> None:
        await log_in(api)

        response = await api.delete("/account")

        assert response.json() == {"ended_at_telegram": True}
        assert platform.ended == ["SESSION-STRING-1"]
        assert (await api.get("/state")).json()["account"]["status"] == "logged_out"

    async def test_an_unreachable_telegram_still_forgets_the_account(self, app, api, platform) -> None:
        """An account the operator asked to forget must not stay usable here because Telegram was briefly down."""
        await log_in(api)
        platform.log_out_error = ConnectionError("down")

        response = await api.delete("/account")

        assert response.json() == {"ended_at_telegram": False}
        assert (await api.get("/state")).json()["account"]["status"] == "logged_out"


@pytest.mark.db
class TestTheOwnerAccountDrivesTheBots:
    async def test_creating_uses_the_stored_session(self, api, platform, db) -> None:
        await log_in(api)
        token = builders.token_for(778899)
        platform.conversation = FakeCreatorBot(reply=fakes.botfather_success(token, "alertsbot"))

        response = await api.post("/bots/created", json={"title": "Alerts", "username": "alertsbot"})

        assert response.status_code == 201
        assert platform.creator_sessions == ["SESSION-STRING-1"]

    async def test_a_session_ended_from_the_phone_is_refused_and_remembered(
        self, api, platform
    ) -> None:
        await log_in(api)
        platform.conversation = FakeCreatorBot(reply=SessionRejected())

        response = await api.post("/bots/created", json={"title": "Alerts", "username": "alertsbot"})
        state = (await api.get("/state")).json()

        assert response.status_code == 409
        assert "rejected" in response.json()["detail"]["detail"]
        assert state["account"]["status"] == "needs_login"
        assert state["can_create_bots"] is False

    async def test_logged_out_the_bot_routes_refuse_and_say_why(self, api) -> None:
        response = await api.post("/bots/created", json={"title": "Alerts", "username": "alertsbot"})

        assert response.status_code == 501
        assert "no Telegram account is logged in" in response.json()["detail"]["detail"]


@pytest.mark.db
class TestRotatingAToken:
    NEW = "778899:" + "N" * 35

    async def rotate(self, api, platform, db, reply: str):
        await log_in(api)
        bot = await builders.bot(db, username="alertsbot", created_here=True, telegram_id=778899)
        platform.conversation = FakeCreatorBot(on_revoke=reply)
        return bot, await api.post("/bots/alertsbot/token")

    async def test_the_new_token_replaces_the_old_and_the_destinations_survive(
        self, api, platform, db, app
    ) -> None:
        await log_in(api)
        bot = await builders.bot(db, username="alertsbot", created_here=True, telegram_id=778899)
        destination = await builders.destination(db, name="operator", bot_id=bot.id)
        await db.execute(
            "UPDATE destinations SET chat_id = 5, state = 'ready', bound_at = now() WHERE id = $1",
            destination.id,
        )
        new = f"{bot.telegram_id}:" + "N" * 35
        platform.conversation = FakeCreatorBot(on_revoke=fakes.botfather_success(new, "alertsbot"))
        app.state.telegram = FakeBotApi(me={"id": bot.telegram_id, "username": "alertsbot"})

        response = await api.post("/bots/alertsbot/token")
        sent = await api.post("/messages", json={"recipient": "operator", "text": "hi"})

        assert response.status_code == 200
        assert new not in response.text
        assert sent.status_code == 200
        assert app.state.telegram.sent[0][0] == new

    async def test_a_reply_without_a_token_changes_nothing(self, api, platform, db) -> None:
        bot, response = await self.rotate(api, platform, db, "I cannot do that.")
        credential = await store.credential_of(db, bot.id)

        assert response.status_code == 502
        assert credential is not None and credential.token == builders.token_for(bot.telegram_id)

    async def test_a_token_that_belongs_to_another_bot_is_not_taken(
        self, api, platform, db, app
    ) -> None:
        await log_in(api)
        bot = await builders.bot(db, username="alertsbot", created_here=True, telegram_id=778899)
        platform.conversation = FakeCreatorBot(
            on_revoke=fakes.botfather_success("123456:" + "Z" * 35, "alertsbot")
        )
        app.state.telegram = FakeBotApi(me={"id": 123456, "username": "someoneelse"})

        response = await api.post("/bots/alertsbot/token")
        credential = await store.credential_of(db, bot.id)

        assert response.status_code == 502
        assert credential is not None and credential.token == builders.token_for(bot.telegram_id)


class TestWhereTelegramSaidTheCodeWent:
    @pytest.mark.parametrize(
        ("kind", "expected"),
        [
            ("SentCodeTypeApp", "app"),
            ("SentCodeTypeSms", "sms"),
            ("SentCodeTypeCall", "call"),
            ("SentCodeTypeFlashCall", "call"),
            ("SentCodeTypeEmailCode", "other"),
        ],
    )
    def test_by_the_class_of_telegrams_answer_and_other_for_what_it_does_not_know(
        self, kind: str, expected: str
    ) -> None:
        from types import SimpleNamespace

        from telegram_gateway.account import _delivery_of

        sent = SimpleNamespace(type=type(kind, (), {})())

        assert _delivery_of(sent) == expected

    @pytest.mark.db
    async def test_the_answer_says_when_telegram_offers_no_other_way(self, api, platform) -> None:
        """The button that asks again is only worth showing when Telegram would answer it with something."""
        platform.login = FakeLoginClient(can_resend=False)

        started = await api.post("/account/login", json={"phone": PHONE})

        assert started.json()["can_resend"] is False


async def _settle() -> None:
    """Lets the QR watcher run what it was woken for."""
    import asyncio

    for _ in range(5):
        await asyncio.sleep(0)


@pytest.mark.db
class TestLoggingInByQrCode:
    async def test_a_scan_logs_the_account_in_without_any_code_being_sent(self, api, platform) -> None:
        started = await api.post("/account/login/qr")
        waiting = await api.get("/account/login/qr")
        platform.login.scanned.set()
        await _settle()
        done = await api.get("/account/login/qr")

        assert started.json()["status"] == "waiting"
        assert started.json()["url"] == "tg://login?token=first"
        assert waiting.json()["status"] == "waiting"
        assert done.json()["status"] == "done"
        assert done.json()["account"]["username"] == "ownerbot_account"
        assert platform.login.phone is None, "no code was ever asked for"
        assert (await api.get("/account/login/qr")).status_code == 409

    async def test_an_account_with_a_password_asks_for_it_after_the_scan(self, api, platform) -> None:
        platform.login = FakeLoginClient(password="hunter2")
        await api.post("/account/login/qr")
        platform.login.scanned.set()
        await _settle()

        asked = await api.get("/account/login/qr")
        done = await api.post("/account/login/password", json={"password": "hunter2"})

        assert asked.json()["status"] == "password"
        assert done.json()["step"] == "done"

    async def test_an_expired_code_is_replaced_by_a_fresh_one(self, api, platform) -> None:
        platform.login.expire_first = True
        await api.post("/account/login/qr")
        await _settle()

        state = (await api.get("/account/login/qr")).json()

        assert state["status"] == "waiting"
        assert state["url"].startswith("tg://login?token=renewed")
