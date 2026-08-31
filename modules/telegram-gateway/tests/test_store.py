"""What the door holds: bots it may speak as, destinations it may speak to, and the one-shot secrets
between the two. Plus the rule that shapes the whole file — a read never carries a token."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import builders
import pytest

from telegram_gateway import store
from telegram_gateway.models import Bot, DestinationState

NOON = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)

pytestmark = pytest.mark.db


class TestTheTokenDoesNotLeak:
    async def test_no_read_a_response_is_built_from_carries_the_token(self, db) -> None:
        """Every read a route or a tool would answer with, called for real, against a token distinctive
        enough to find anywhere in what came back. This is the leak worth a test of its own: a token in
        a response looks exactly like a working feature, and it is a credential to write as this system.
        """
        added = await builders.bot(db)
        bound = await builders.destination(db, name="operator", bot_id=added.id)
        await store.issue_nonce(
            db, nonce="s3cret", destination_id=bound.id, expires_at=NOON + timedelta(hours=1)
        )
        secret = builders.token_for(added.telegram_id)

        answers = [
            await store.list_bots(db),
            await store.bot_by_username(db, added.username),
            await store.list_destinations(db),
            await store.destination_by_name(db, "operator"),
            await store.binding_for(db, "s3cret"),
        ]

        assert all(isinstance(entry, Bot) for entry in answers[0])
        assert secret not in repr(answers)

    async def test_the_credential_is_reachable_through_its_own_function(self, db) -> None:
        """Fetched by the code about to make a request with it, and by nothing that builds a response.
        A separate type rather than an optional field on `Bot`: an optional field is one forgotten
        `exclude` away from a response."""
        added = await builders.bot(db)

        credential = await store.credential_of(db, added.id)

        assert credential is not None
        assert credential.token == builders.token_for(added.telegram_id)


class TestBots:
    async def test_the_same_bot_added_twice_is_one_row(self, db) -> None:
        """Keyed on Telegram's own id, not on the name it was given here."""
        first = await builders.bot(db, username="alertsbot")
        again = await store.add_bot(
            db,
            telegram_id=first.telegram_id,
            username="alertsbot",
            title="Renamed",
            token=builders.token_for(first.telegram_id),
            created_here=False,
        )

        assert again.id == first.id
        assert again.title == "Renamed"
        assert len(await store.list_bots(db)) == 1

    async def test_re_adding_replaces_the_token(self, db) -> None:
        """How a revoked token is replaced: the operator adds the bot again."""
        added = await builders.bot(db)

        await store.add_bot(
            db,
            telegram_id=added.telegram_id,
            username=added.username,
            title=added.title,
            token="999:" + "B" * 35,
            created_here=False,
        )

        credential = await store.credential_of(db, added.id)
        assert credential is not None
        assert credential.token == "999:" + "B" * 35

    async def test_removing_a_bot_takes_its_destinations(self, db) -> None:
        """A destination without a bot has nothing to send through."""
        added = await builders.bot(db)
        await builders.destination(db, name="operator", bot_id=added.id)

        assert await store.remove_bot(db, added.id)

        assert await store.list_destinations(db) == []

    async def test_the_count_is_what_the_ceiling_is_read_from(self, db) -> None:
        await builders.bot(db)
        await builders.bot(db)

        assert await store.count_bots(db) == 2


class TestDestinations:
    async def test_a_new_destination_cannot_receive_yet(self, db) -> None:
        """A bot may not speak first, so a destination is an intention before it is an address."""
        created = await builders.destination(db, name="operator")

        assert created.state is DestinationState.PENDING
        assert created.chat_id is None
        assert created.receives is False

    async def test_the_secret_turns_the_intention_into_an_address(self, db) -> None:
        created = await builders.destination(db, name="operator")
        await store.issue_nonce(
            db, nonce="s3cret", destination_id=created.id, expires_at=NOON + timedelta(hours=1)
        )

        bound = await store.bind_destination(db, nonce="s3cret", chat_id=4242, moment=NOON)

        assert bound is not None
        assert bound.receives is True
        assert bound.chat_id == 4242

    async def test_the_same_secret_binds_only_once(self, db) -> None:
        created = await builders.destination(db, name="operator")
        await store.issue_nonce(
            db, nonce="s3cret", destination_id=created.id, expires_at=NOON + timedelta(hours=1)
        )
        await store.bind_destination(db, nonce="s3cret", chat_id=4242, moment=NOON)

        again = await store.bind_destination(db, nonce="s3cret", chat_id=9999, moment=NOON)

        assert again is None
        found = await store.destination_by_name(db, "operator")
        assert found is not None and found.chat_id == 4242

    async def test_an_expired_secret_binds_nothing(self, db) -> None:
        created = await builders.destination(db, name="operator")
        await store.issue_nonce(
            db, nonce="stale", destination_id=created.id, expires_at=NOON - timedelta(minutes=1)
        )

        assert await store.bind_destination(db, nonce="stale", chat_id=4242, moment=NOON) is None

    async def test_a_secret_that_never_existed_is_told_apart_from_a_spent_one(self, db) -> None:
        """Both refuse to bind, and the record of the spent one survives so the two stay different
        questions — one is a replay, the other is somebody guessing."""
        created = await builders.destination(db, name="operator")
        await store.issue_nonce(
            db, nonce="s3cret", destination_id=created.id, expires_at=NOON + timedelta(hours=1)
        )
        await store.bind_destination(db, nonce="s3cret", chat_id=4242, moment=NOON)

        spent = await store.binding_for(db, "s3cret")
        assert spent is not None and spent.used_at is not None
        assert await store.binding_for(db, "never-issued") is None

    async def test_blocking_keeps_the_destination(self, db) -> None:
        """What is gone is consent, not the intention — and it comes back with a second start."""
        created = await builders.destination(db, name="operator")
        await store.issue_nonce(
            db, nonce="s3cret", destination_id=created.id, expires_at=NOON + timedelta(hours=1)
        )
        await store.bind_destination(db, nonce="s3cret", chat_id=4242, moment=NOON)

        await store.mark_blocked(db, created.id, NOON + timedelta(days=1))

        found = await store.destination_by_name(db, "operator")
        assert found is not None
        assert found.state is DestinationState.BLOCKED
        assert found.receives is False

    async def test_binding_again_clears_a_block(self, db) -> None:
        created = await builders.destination(db, name="operator")
        await store.issue_nonce(
            db, nonce="one", destination_id=created.id, expires_at=NOON + timedelta(hours=1)
        )
        await store.bind_destination(db, nonce="one", chat_id=4242, moment=NOON)
        await store.mark_blocked(db, created.id, NOON)
        await store.issue_nonce(
            db, nonce="two", destination_id=created.id, expires_at=NOON + timedelta(hours=2)
        )

        rebound = await store.bind_destination(db, nonce="two", chat_id=4242, moment=NOON)

        assert rebound is not None
        assert rebound.state is DestinationState.READY
        assert rebound.blocked_at is None

    async def test_removing_a_destination_leaves_the_bot_and_its_siblings(self, db) -> None:
        carrier = await builders.bot(db)
        await builders.destination(db, name="first", bot_id=carrier.id)
        await builders.destination(db, name="second", bot_id=carrier.id)

        assert await store.remove_destination(db, "first")

        assert len(await store.list_bots(db)) == 1
        assert [d.name for d in await store.list_destinations(db)] == ["second"]


class TestTheUpdateCursor:
    async def test_the_cursor_survives_a_restart(self, db) -> None:
        """Forgetting it re-reads updates already acted on, and a start command replayed that way
        would rebuild a destination the operator had removed."""
        carrier = await builders.bot(db)

        await store.note_offset(db, carrier.id, 17)

        assert await store.next_offset(db, carrier.id) == 17

    async def test_the_cursor_never_moves_backwards(self, db) -> None:
        """Two pollers of one bot is a state this module does not intend, and an out-of-order write
        would replay updates rather than merely duplicate work."""
        carrier = await builders.bot(db)
        await store.note_offset(db, carrier.id, 17)

        await store.note_offset(db, carrier.id, 9)

        assert await store.next_offset(db, carrier.id) == 17

    async def test_a_bot_never_polled_starts_at_zero(self, db) -> None:
        carrier = await builders.bot(db)

        assert await store.next_offset(db, carrier.id) == 0
