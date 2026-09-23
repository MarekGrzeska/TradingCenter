"""What the door to Telegram holds: the bots it can speak as, the destinations it can speak to, and the
one-shot secrets that turn a tap into a destination. No message table — the gateway does not remember
what it sent, and `telegram-gateway-delivery` says why.

Revision ID: 0001
Revises:
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE bots (
            id           bigserial PRIMARY KEY,
            -- Telegram's own numeric id for the bot, parsed out of the token. Unique so the same bot
            -- added twice by two names is one row, however it arrived.
            telegram_id  bigint NOT NULL UNIQUE,
            -- The @name, without the @. What a start link is built from.
            username     text NOT NULL UNIQUE,
            title        text NOT NULL,
            -- The credential. It is never selected by a read this module publishes, and never logged —
            -- `telegram-gateway-bots` makes that a requirement with its own test.
            token        text NOT NULL,
            -- Whether this module created it through the creator bot, or the operator pasted it. Kept
            -- because deleting a bot is only offered for the ones this module made.
            created_here boolean NOT NULL DEFAULT false,
            added_at     timestamptz NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE destinations (
            id          bigserial PRIMARY KEY,
            -- What a caller addresses. A name rather than a chat id, so every caller does not end up
            -- holding its own copy of a number that changes when the bot does.
            name        text NOT NULL UNIQUE,
            bot_id      bigint NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
            -- Null until somebody has opened the conversation: a bot cannot speak first, so a
            -- destination exists as an intention before it exists as somewhere to send.
            chat_id     bigint,
            -- 'pending' before the tap, 'ready' after it, 'blocked' once Telegram says the bot was
            -- blocked. A blocked destination is not deleted: it is waiting for a second /start.
            state       text NOT NULL DEFAULT 'pending'
                        CHECK (state IN ('pending', 'ready', 'blocked')),
            bound_at    timestamptz,
            blocked_at  timestamptz,
            created_at  timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX destinations_bot_idx ON destinations (bot_id)")
    # One conversation is one destination. Partial, because several destinations may sit unbound at
    # once and NULL is not a duplicate of NULL for a unique index either way — stated so the intent
    # survives somebody adding a second column to the key.
    op.execute(
        "CREATE UNIQUE INDEX destinations_chat_idx ON destinations (bot_id, chat_id) "
        "WHERE chat_id IS NOT NULL"
    )

    op.execute(
        """
        CREATE TABLE binding_nonces (
            -- The secret itself is the key: it arrives from Telegram as text in a /start command, and
            -- looking it up is the only thing ever done with it.
            nonce          text PRIMARY KEY,
            destination_id bigint NOT NULL REFERENCES destinations(id) ON DELETE CASCADE,
            expires_at     timestamptz NOT NULL,
            -- Set when it binds. Kept rather than deleted so a second arrival of the same secret is
            -- answered "already used" rather than "never existed" — the two are different mistakes.
            used_at        timestamptz,
            issued_at      timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX binding_nonces_destination_idx ON binding_nonces (destination_id)")

    op.execute(
        """
        CREATE TABLE update_offsets (
            -- Telegram's long-poll cursor, per bot. Kept in the database rather than in memory because
            -- a restart that forgets it re-reads updates already acted on, and a /start replayed after
            -- a restart would bind a destination the operator had since removed.
            bot_id     bigint PRIMARY KEY REFERENCES bots(id) ON DELETE CASCADE,
            next_offset bigint NOT NULL DEFAULT 0,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE update_offsets")
    op.execute("DROP TABLE binding_nonces")
    op.execute("DROP TABLE destinations")
    op.execute("DROP TABLE bots")
