"""Creating a bot without opening Telegram — and the four refusals that come before a word is sent."""

from __future__ import annotations

import logging

import builders
import fakes
import pytest

from telegram_gateway import bots, creator, store
from telegram_gateway.errors import (
    CreatingBotsUnavailable,
    CreatorBotUnreadable,
    TooManyBots,
)

TOKEN = "778899:AAHveryveryverysecretveryverysecre1"


class TestReadingTheCreatorBot:
    def test_the_token_is_found_inside_a_paragraph_of_prose(self) -> None:
        """@BotFather answers in a natural language Telegram may reword without notice, so what is
        looked for is the token itself rather than a phrase around it."""
        assert creator.token_in(fakes.botfather_success(TOKEN)) == TOKEN

    def test_a_reply_with_no_token_is_a_refusal_carrying_the_whole_reply(self) -> None:
        """Guessing that it probably worked would leave a bot alive that nobody has the token for."""
        with pytest.raises(CreatorBotUnreadable, match="Sorry, this username is already taken"):
            creator.token_in("Sorry, this username is already taken. Please try something else.")

    def test_a_cheerful_reply_without_a_token_is_still_a_refusal(self) -> None:
        """"It did not look like an error" is not the same claim as "there is a token in it"."""
        with pytest.raises(CreatorBotUnreadable):
            creator.token_in("Done! Your bot is ready.")


class TestTheUsernameRule:
    def test_a_username_telegram_would_reject_is_caught_here(self) -> None:
        """Learned from Telegram's documentation rather than from a refusal mid-conversation, which
        costs a round of an exchange held on the operator's own account."""
        with pytest.raises(ValueError, match="ending in 'bot'"):
            creator.usable_username("alerts")

    def test_a_leading_at_sign_is_not_part_of_the_name(self) -> None:
        assert creator.usable_username("@alertsbot") == "alertsbot"


class TestWhatIsCheckedBeforeSpeaking:
    def test_no_account_session_names_the_settings(self) -> None:
        """A supported state, not a fault: the module sends without them, and only creating needs a
        credential to the operator's personal Telegram."""
        with pytest.raises(CreatingBotsUnavailable, match="TELEGRAM_API_ID"):
            creator.guard(can_create=False, held=0, ceiling=20)

    def test_the_ceiling_refuses_before_telegram_is_asked(self) -> None:
        with pytest.raises(TooManyBots, match="Nothing was asked of Telegram"):
            creator.guard(can_create=True, held=20, ceiling=20)

    def test_room_under_the_ceiling_passes(self) -> None:
        creator.guard(can_create=True, held=19, ceiling=20)


@pytest.mark.db
class TestCreating:
    async def test_a_created_bot_is_stored_with_the_identity_telegram_reported(self, db) -> None:
        """The numeric id comes out of the token rather than from a second round trip, and it is a
        fact about the bot rather than something the caller chose."""
        bot = fakes.FakeCreatorBot(reply=fakes.botfather_success(TOKEN))

        stored = await bots.create(
            db, bot, title="Alerts", username="alertsbot", can_create=True, ceiling=20
        )

        assert stored.telegram_id == 778899
        assert stored.username == "alertsbot"
        assert stored.created_here is True
        assert bot.created == [("Alerts", "alertsbot")]

    async def test_the_token_is_kept_and_never_returned(self, db) -> None:
        bot = fakes.FakeCreatorBot(reply=fakes.botfather_success(TOKEN))

        stored = await bots.create(
            db, bot, title="Alerts", username="alertsbot", can_create=True, ceiling=20
        )

        assert TOKEN not in repr(stored)
        credential = await store.credential_of(db, stored.id)
        assert credential is not None and credential.token == TOKEN

    async def test_the_token_does_not_reach_the_log(self, db, caplog) -> None:
        """The most dangerous log line in this module: it happens exactly once per bot, at the moment
        a live credential is in a local variable."""
        bot = fakes.FakeCreatorBot(reply=fakes.botfather_success(TOKEN))

        with caplog.at_level(logging.DEBUG):
            await bots.create(
                db, bot, title="Alerts", username="alertsbot", can_create=True, ceiling=20
            )

        assert TOKEN not in caplog.text
        assert "alertsbot" in caplog.text

    async def test_without_a_session_nothing_is_said_to_telegram(self, db) -> None:
        bot = fakes.FakeCreatorBot(reply=fakes.botfather_success(TOKEN))

        with pytest.raises(CreatingBotsUnavailable):
            await bots.create(
                db, bot, title="Alerts", username="alertsbot", can_create=False, ceiling=20
            )

        assert bot.created == []
        assert await store.list_bots(db) == []

    async def test_at_the_ceiling_nothing_is_said_to_telegram(self, db) -> None:
        """A refusal from Telegram would still cost an attempt counted against the operator's
        account — a resource whose exhaustion reaches them outside this system."""
        await builders.bot(db)
        await builders.bot(db)
        bot = fakes.FakeCreatorBot(reply=fakes.botfather_success(TOKEN))

        with pytest.raises(TooManyBots, match="already holds 2"):
            await bots.create(
                db, bot, title="Alerts", username="alertsbot", can_create=True, ceiling=2
            )

        assert bot.created == []

    async def test_an_unreadable_reply_stores_no_bot(self, db) -> None:
        bot = fakes.FakeCreatorBot(reply="Sorry, too many attempts. Please try again later.")

        with pytest.raises(CreatorBotUnreadable, match="too many attempts"):
            await bots.create(
                db, bot, title="Alerts", username="alertsbot", can_create=True, ceiling=20
            )

        assert await store.list_bots(db) == []


@pytest.mark.db
class TestAdopting:
    async def test_a_pasted_token_asks_telegram_who_it_belongs_to(self, db) -> None:
        """The @name and the id are facts about the bot, not preferences about it, so neither is
        taken from whoever pasted the token."""
        api = fakes.FakeBotApi(me={"id": 778899, "username": "pastedbot", "first_name": "Pasted"})

        stored = await bots.adopt(db, api, token=TOKEN)

        assert (stored.telegram_id, stored.username) == (778899, "pastedbot")
        assert stored.created_here is False


@pytest.mark.db
class TestDeleting:
    async def test_telegram_first_then_the_row(self, db) -> None:
        """A row deleted before the conversation succeeds leaves a bot alive that this module can no
        longer name — and it still counts against the account's ceiling."""
        existing = await builders.bot(db, username="alertsbot", created_here=True)
        bot = fakes.FakeCreatorBot(on_delete="Done! The bot is gone.")

        await bots.destroy(db, bot, existing=existing, can_create=True)

        assert bot.deleted == ["alertsbot"]
        assert await store.list_bots(db) == []

    async def test_a_failed_conversation_keeps_the_row(self, db) -> None:
        existing = await builders.bot(db, username="alertsbot", created_here=True)
        bot = fakes.FakeCreatorBot(on_delete=RuntimeError("BotFather did not answer"))

        with pytest.raises(RuntimeError):
            await bots.destroy(db, bot, existing=existing, can_create=True)

        assert len(await store.list_bots(db)) == 1

    async def test_without_a_session_nothing_is_deleted(self, db) -> None:
        existing = await builders.bot(db, username="alertsbot", created_here=True)
        bot = fakes.FakeCreatorBot()

        with pytest.raises(CreatingBotsUnavailable):
            await bots.destroy(db, bot, existing=existing, can_create=False)

        assert bot.deleted == []
        assert len(await store.list_bots(db)) == 1
