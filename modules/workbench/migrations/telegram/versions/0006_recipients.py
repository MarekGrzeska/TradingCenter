"""A recipient is a thing of its own, and a destination is that recipient reached through one bot.

Until now a destination was both: its name was the recipient and its bot the way there, so one person reached through three
bots needed three names. `recipients` holds the name once; `destinations` keeps the conversation (bot, chat, state, the
start link's nonce) and gains `recipient_id`, unique together with the bot.

Expand now, contract later: the `name` column stays, as a copy without the uniqueness, so an image from before this
migration still reads and writes the table until no recipient has two bots. A later change drops it.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE recipients (
            id          bigserial PRIMARY KEY,
            name        text NOT NULL UNIQUE,
            created_at  timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("INSERT INTO recipients (name, created_at) SELECT name, min(created_at) FROM destinations GROUP BY name")
    op.execute("ALTER TABLE destinations ADD COLUMN recipient_id bigint")
    op.execute("UPDATE destinations d SET recipient_id = r.id FROM recipients r WHERE r.name = d.name")
    op.execute("ALTER TABLE destinations ALTER COLUMN recipient_id SET NOT NULL")
    op.execute(
        "ALTER TABLE destinations ADD CONSTRAINT destinations_recipient_fkey "
        "FOREIGN KEY (recipient_id) REFERENCES recipients(id) ON DELETE CASCADE"
    )
    op.execute("ALTER TABLE destinations ADD CONSTRAINT destinations_recipient_bot_key UNIQUE (recipient_id, bot_id)")
    op.execute("ALTER TABLE destinations DROP CONSTRAINT destinations_name_key")


def downgrade() -> None:
    # Only reversible while no recipient has two bots: the old schema cannot hold the second row.
    op.execute("ALTER TABLE destinations ADD CONSTRAINT destinations_name_key UNIQUE (name)")
    op.execute("ALTER TABLE destinations DROP CONSTRAINT destinations_recipient_bot_key")
    op.execute("ALTER TABLE destinations DROP CONSTRAINT destinations_recipient_fkey")
    op.execute("ALTER TABLE destinations DROP COLUMN recipient_id")
    op.execute("DROP TABLE recipients")
