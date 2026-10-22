"""A rule may name the bot it tells through.

Empty means the recipient's only bot, which is what every rule written before a recipient could be reached through
several bots means; nothing is converted, because the old meaning is still true for every recipient that has one bot.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE rules ADD COLUMN bot text")


def downgrade() -> None:
    op.execute("ALTER TABLE rules DROP COLUMN bot")
