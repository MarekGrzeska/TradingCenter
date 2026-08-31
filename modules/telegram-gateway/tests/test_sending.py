"""Sending one message, and the four ways it is refused. Plus the rule that costs nothing until the
day it saves everything: a token never reaches a log."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import builders
import fakes
import httpx
import pytest
import respx

from telegram_gateway import redaction, sending, store
from telegram_gateway.bot_api import bot_api
from telegram_gateway.errors import (
    Blocked,
    DestinationNotReady,
    MessageTooLong,
    NoSuchDestination,
    RateLimited,
    TelegramRefused,
    TelegramUnreachable,
)
from telegram_gateway.models import DestinationState

NOON = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
CEILING = 4096

TOKEN = "123456:AAHveryveryverysecretveryverysecre1"
BASE = "https://api.telegram.example"


async def ready_destination(db, name: str = "operator"):
    """A destination somebody has already opened the conversation with.

    Dated from the real clock, not a fixed noon: the send path asks `datetime.now`, so a fixture
    pinned to a moment already past hands every test an expired secret.
    """
    now = datetime.now(UTC)
    created = await builders.destination(db, name=name)
    await store.issue_nonce(
        db, nonce=f"n-{name}", destination_id=created.id, expires_at=now + timedelta(hours=1)
    )
    return await store.bind_destination(db, nonce=f"n-{name}", chat_id=4242, moment=now)


@pytest.mark.db
class TestSending:
    async def test_a_message_reaches_the_named_destination(self, db) -> None:
        await ready_destination(db)
        api = fakes.FakeBotApi()

        delivered = await sending.send(
            db, api, name="operator", text="US100 broke out", max_chars=CEILING
        )

        assert delivered.chat_id == 4242
        [(_, chat_id, text)] = api.sent
        assert (chat_id, text) == (4242, "US100 broke out")

    async def test_an_unknown_name_is_refused_without_a_request(self, db) -> None:
        api = fakes.FakeBotApi()

        with pytest.raises(NoSuchDestination, match="not a destination"):
            await sending.send(db, api, name="nobody", text="hi", max_chars=CEILING)

        assert api.sent == []

    async def test_a_destination_nobody_has_started_is_a_different_refusal(self, db) -> None:
        """The name is right and the move is a start link, not a correction — so it must not read
        as "no such destination"."""
        await builders.destination(db, name="operator")
        api = fakes.FakeBotApi()

        with pytest.raises(DestinationNotReady, match="tap its start link"):
            await sending.send(db, api, name="operator", text="hi", max_chars=CEILING)

        assert api.sent == []

    async def test_too_long_is_refused_rather_than_shortened(self, db) -> None:
        """A truncated alert is an alert about something else, and nothing in a success response
        would say so."""
        await ready_destination(db)
        api = fakes.FakeBotApi()

        with pytest.raises(MessageTooLong, match="refused rather than shortened"):
            await sending.send(db, api, name="operator", text="x" * (CEILING + 1), max_chars=CEILING)

        assert api.sent == []

    async def test_a_rate_limit_carries_the_wait_telegram_asked_for(self, db) -> None:
        """There is no queue here, so this is the caller's to act on — and its "already told"
        marker must stay unset, or the notification is lost rather than delayed."""
        await ready_destination(db)
        api = fakes.FakeBotApi(send=RateLimited(retry_after_seconds=30))

        with pytest.raises(RateLimited) as refusal:
            await sending.send(db, api, name="operator", text="hi", max_chars=CEILING)

        assert refusal.value.retry_after_seconds == 30

    async def test_a_block_marks_the_destination_and_names_it(self, db) -> None:
        await ready_destination(db)
        api = fakes.FakeBotApi(send=Blocked(name=""))

        with pytest.raises(Blocked, match="operator"):
            await sending.send(db, api, name="operator", text="hi", max_chars=CEILING)

        found = await store.destination_by_name(db, "operator")
        assert found is not None
        assert found.state is DestinationState.BLOCKED

    async def test_a_blocked_destination_costs_no_further_requests(self, db) -> None:
        await ready_destination(db)
        blocking = fakes.FakeBotApi(send=Blocked(name=""))
        with pytest.raises(Blocked):
            await sending.send(db, blocking, name="operator", text="hi", max_chars=CEILING)

        after = fakes.FakeBotApi()
        with pytest.raises(DestinationNotReady, match="blocked the bot"):
            await sending.send(db, after, name="operator", text="hi", max_chars=CEILING)

        assert after.sent == []

    async def test_nothing_is_recorded_about_what_was_sent(self, db) -> None:
        """The gateway does not remember. Asserted here because "no message table" is a promise the
        schema keeps, and a later convenience column would break it quietly."""
        await ready_destination(db)
        await sending.send(db, fakes.FakeBotApi(), name="operator", text="secret plan", max_chars=CEILING)

        tables = await db.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = current_schema()"
        )
        assert not any("message" in row["tablename"] for row in tables)


class TestTheTokenNeverReachesALog:
    """The token is part of the request path, so the URL *is* the credential, and logging a failing
    request is the most ordinary way to lose one.

    `httpx` logs every request it makes at INFO — URL included — so sanitising only this module's own
    messages left the token in the log anyway. These run through the same filter the application
    installs, because that is the thing under test.
    """

    @pytest.fixture(autouse=True)
    def _redacting(self, caplog):
        with caplog.at_level(logging.DEBUG):
            redaction.install()
            yield

    @respx.mock
    async def test_an_unreachable_telegram_reports_without_the_token(self, caplog) -> None:
        respx.post(f"{BASE}/bot{TOKEN}/sendMessage").mock(
            side_effect=httpx.ConnectError("failed to connect", request=httpx.Request("POST", f"{BASE}/bot{TOKEN}/sendMessage"))
        )

        async with bot_api(BASE) as api:
            with pytest.raises(TelegramUnreachable) as refusal:
                await api.send_message(TOKEN, chat_id=1, text="hi")

        assert TOKEN not in str(refusal.value)
        assert TOKEN not in caplog.text

    @respx.mock
    async def test_a_refusal_quoting_the_url_reports_without_the_token(self, caplog) -> None:
        """Telegram's own `description` sometimes echoes the request, which is how a token ends up
        in a message this module did not write."""
        respx.post(f"{BASE}/bot{TOKEN}/sendMessage").mock(
            return_value=httpx.Response(
                400,
                json={"ok": False, "description": f"Bad Request at /bot{TOKEN}/sendMessage"},
            )
        )

        async with bot_api(BASE) as api:
            with pytest.raises(TelegramRefused) as refusal:
                await api.send_message(TOKEN, chat_id=1, text="hi")

        assert TOKEN not in str(refusal.value)
        assert "<token>" in str(refusal.value)
        assert TOKEN not in caplog.text
        assert "<token>" in caplog.text, "substituted, not stripped — a blank reads as no token"


class TestReadingTelegramsAnswer:
    @respx.mock
    async def test_a_rate_limit_becomes_its_own_refusal(self) -> None:
        respx.post(f"{BASE}/bot{TOKEN}/sendMessage").mock(
            return_value=httpx.Response(
                429,
                json={
                    "ok": False,
                    "description": "Too Many Requests",
                    "parameters": {"retry_after": 12},
                },
            )
        )

        async with bot_api(BASE) as api:
            with pytest.raises(RateLimited) as refusal:
                await api.send_message(TOKEN, chat_id=1, text="hi")

        assert refusal.value.retry_after_seconds == 12

    @respx.mock
    async def test_a_block_is_told_apart_from_a_revoked_token(self) -> None:
        """Both are a plain 403, and the operator's move differs: one is a start link, the other is
        a new token."""
        respx.post(f"{BASE}/bot{TOKEN}/sendMessage").mock(
            return_value=httpx.Response(
                403, json={"ok": False, "description": "Forbidden: bot was blocked by the user"}
            )
        )

        async with bot_api(BASE) as api:
            with pytest.raises(Blocked):
                await api.send_message(TOKEN, chat_id=1, text="hi")

    @respx.mock
    async def test_another_403_stays_an_ordinary_refusal(self) -> None:
        respx.post(f"{BASE}/bot{TOKEN}/sendMessage").mock(
            return_value=httpx.Response(403, json={"ok": False, "description": "Unauthorized"})
        )

        async with bot_api(BASE) as api:
            with pytest.raises(TelegramRefused, match="Unauthorized"):
                await api.send_message(TOKEN, chat_id=1, text="hi")

    @respx.mock
    async def test_a_body_that_is_not_json_is_unreachable_rather_than_a_crash(self) -> None:
        respx.post(f"{BASE}/bot{TOKEN}/sendMessage").mock(
            return_value=httpx.Response(502, text="<html>bad gateway</html>")
        )

        async with bot_api(BASE) as api:
            with pytest.raises(TelegramUnreachable, match="not JSON"):
                await api.send_message(TOKEN, chat_id=1, text="hi")

    @respx.mock
    async def test_a_delivered_message_carries_what_telegram_assigned(self) -> None:
        respx.post(f"{BASE}/bot{TOKEN}/sendMessage").mock(
            return_value=httpx.Response(
                200,
                json={"ok": True, "result": {"message_id": 77, "chat": {"id": 4242}}},
            )
        )

        async with bot_api(BASE) as api:
            delivered = await api.send_message(TOKEN, chat_id=4242, text="hi")

        assert (delivered.message_id, delivered.chat_id) == (77, 4242)
