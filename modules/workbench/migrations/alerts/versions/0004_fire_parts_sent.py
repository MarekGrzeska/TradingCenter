"""How much of a fire has arrived.

A message longer than Telegram takes is sent as several, and a retry after the second failed must start at the second:
the first is already on the phone. Every fire written before has one part and none of it sent, which is the default.

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
    op.execute("ALTER TABLE fires ADD COLUMN parts_sent integer NOT NULL DEFAULT 0")


def downgrade() -> None:
    op.execute("ALTER TABLE fires DROP COLUMN parts_sent")
