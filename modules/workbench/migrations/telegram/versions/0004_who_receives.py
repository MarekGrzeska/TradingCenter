"""Who a destination is on Telegram: the @name, the display name and whether it is a person or a group, as Telegram
reported them when the chat was bound (or when the gateway asked later). Shown, never addressed by: the chat id stays the
address, because a @name can change hands.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE destinations
            ADD COLUMN chat_username text,
            ADD COLUMN chat_title    text,
            ADD COLUMN chat_kind     text
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE destinations DROP COLUMN chat_kind, DROP COLUMN chat_title, DROP COLUMN chat_username"
    )
