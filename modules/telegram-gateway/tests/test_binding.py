"""Turning a tap into a destination: the link, the one-shot secret coming back, and the cursor that
makes a restart harmless."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import builders
import fakes
import pytest

from telegram_gateway import binding, store
from telegram_gateway.models import DestinationState

pytestmark = pytest.mark.db


class TestTheOffer:
    async def test_the_link_points_at_the_bot_and_carries_the_secret(self, db) -> None:
        bot = await builders.bot(db, username="alertsbot")

        destination, link = await binding.offer(db, name="operator", bot=bot)

        assert link.startswith("https://t.me/alertsbot?start=")
        issued = link.split("start=")[1]
        assert await store.binding_for(db, issued) is not None
        assert destination.name == "operator"

    async def test_the_destination_exists_before_it_can_receive(self, db) -> None:
        """The honest shape of a platform where a bot may not speak first: the name is claimed, and
        the address arrives when a person taps."""
        bot = await builders.bot(db)

        destination, _ = await binding.offer(db, name="operator", bot=bot)

        assert destination.state is DestinationState.PENDING
        assert destination.receives is False

    async def test_asking_again_reuses_the_name_and_issues_a_new_secret(self, db) -> None:
        """How a lost link is replaced, and how a blocked destination is re-bound — neither should
        require deleting the name every caller already holds."""
        bot = await builders.bot(db)
        _, first = await binding.offer(db, name="operator", bot=bot)

        _, second = await binding.offer(db, name="operator", bot=bot)

        assert first != second
        assert len(await store.list_destinations(db)) == 1

    async def test_a_secret_is_not_guessable(self, db) -> None:
        """It travels in a URL and in a Telegram message, and it is the only thing between a stranger
        who saw the link and a destination bound to their chat."""
        bot = await builders.bot(db)

        _, link = await binding.offer(db, name="operator", bot=bot)

        assert len(link.split("start=")[1]) >= 20

    async def test_a_secret_expires(self, db) -> None:
        bot = await builders.bot(db)
        issued_at = datetime.now(UTC)

        _, link = await binding.offer(db, name="operator", bot=bot, now=issued_at)

        found = await store.binding_for(db, link.split("start=")[1])
        assert found is not None
        assert found.expires_at <= issued_at + binding.NONCE_LIFETIME


class TestWhatComesBack:
    async def test_a_start_with_the_secret_binds_the_chat_that_sent_it(self, db) -> None:
        bot = await builders.bot(db)
        _, link = await binding.offer(db, name="operator", bot=bot)
        nonce = link.split("start=")[1]

        bound = await binding.consume(
            db, bot, [fakes.start_update(1, chat_id=4242, payload=nonce)]
        )

        assert bound == 1
        found = await store.destination_by_name(db, "operator")
        assert found is not None
        assert found.receives is True
        assert found.chat_id == 4242

    async def test_a_bare_start_binds_nothing(self, db) -> None:
        """Somebody opened the bot without a link. There is nothing to bind it to, and guessing
        would attach a stranger's chat to whatever destination was waiting."""
        bot = await builders.bot(db)
        await binding.offer(db, name="operator", bot=bot)

        bound = await binding.consume(db, bot, [fakes.start_update(1, chat_id=99, payload="")])

        assert bound == 0
        found = await store.destination_by_name(db, "operator")
        assert found is not None and found.receives is False

    async def test_an_unknown_secret_binds_nothing(self, db) -> None:
        bot = await builders.bot(db)
        await binding.offer(db, name="operator", bot=bot)

        bound = await binding.consume(
            db, bot, [fakes.start_update(1, chat_id=99, payload="not-a-real-nonce")]
        )

        assert bound == 0

    async def test_the_same_secret_arriving_twice_binds_once(self, db) -> None:
        bot = await builders.bot(db)
        _, link = await binding.offer(db, name="operator", bot=bot)
        nonce = link.split("start=")[1]
        await binding.consume(db, bot, [fakes.start_update(1, chat_id=4242, payload=nonce)])

        bound = await binding.consume(
            db, bot, [fakes.start_update(2, chat_id=7777, payload=nonce)]
        )

        assert bound == 0
        found = await store.destination_by_name(db, "operator")
        assert found is not None and found.chat_id == 4242

    async def test_an_expired_secret_binds_nothing(self, db) -> None:
        bot = await builders.bot(db)
        _, link = await binding.offer(db, name="operator", bot=bot)
        nonce = link.split("start=")[1]

        bound = await binding.consume(
            db,
            bot,
            [fakes.start_update(1, chat_id=4242, payload=nonce)],
            now=datetime.now(UTC) + binding.NONCE_LIFETIME + timedelta(minutes=1),
        )

        assert bound == 0

    async def test_a_message_that_is_not_a_start_is_ignored(self, db) -> None:
        """This module reads Telegram for exactly one reason."""
        bot = await builders.bot(db)
        chatter = {
            "update_id": 5,
            "message": {"message_id": 5, "chat": {"id": 1}, "text": "what is the price"},
        }

        assert await binding.consume(db, bot, [chatter]) == 0


class TestTheCursor:
    async def test_the_cursor_moves_past_updates_that_bound_nothing(self, db) -> None:
        """Leaving them unacknowledged has Telegram redeliver the same unusable message for as long
        as it keeps it — a poll that never makes progress."""
        bot = await builders.bot(db)

        await binding.consume(db, bot, [fakes.start_update(41, chat_id=1, payload="nope")])

        assert await store.next_offset(db, bot.id) == 42

    async def test_the_cursor_survives_the_binding(self, db) -> None:
        bot = await builders.bot(db)
        _, link = await binding.offer(db, name="operator", bot=bot)

        await binding.consume(
            db, bot, [fakes.start_update(7, chat_id=4242, payload=link.split("start=")[1])]
        )

        assert await store.next_offset(db, bot.id) == 8

    async def test_an_empty_poll_leaves_the_cursor_alone(self, db) -> None:
        bot = await builders.bot(db)
        await store.note_offset(db, bot.id, 12)

        await binding.consume(db, bot, [])

        assert await store.next_offset(db, bot.id) == 12


class TestTheWatcher:
    async def test_a_poll_asks_from_the_stored_cursor(self, pool) -> None:
        """A restart that forgot it would re-read a start command already acted on, and rebuild a
        destination the operator had since removed."""
        async with pool.acquire() as conn:
            bot = await builders.bot(conn)
            await store.note_offset(conn, bot.id, 30)
        api = fakes.FakeBotApi()

        await binding.Watcher(pool, api).poll_once(bot)

        [(_, offset)] = api.update_calls
        assert offset == 30

    async def test_a_poll_binds_what_it_finds(self, pool) -> None:
        async with pool.acquire() as conn:
            bot = await builders.bot(conn)
            _, link = await binding.offer(conn, name="operator", bot=bot)
        nonce = link.split("start=")[1]
        api = fakes.FakeBotApi(updates=[[fakes.start_update(1, chat_id=4242, payload=nonce)]])

        assert await binding.Watcher(pool, api).poll_once(bot) == 1

        async with pool.acquire() as conn:
            found = await store.destination_by_name(conn, "operator")
        assert found is not None and found.receives is True

    async def test_a_bot_removed_mid_poll_is_not_an_error(self, pool) -> None:
        """The watcher and the delete race by construction: one is a background task and the other
        is a route."""
        async with pool.acquire() as conn:
            bot = await builders.bot(conn)
            await store.remove_bot(conn, bot.id)

        assert await binding.Watcher(pool, fakes.FakeBotApi()).poll_once(bot) == 0
