"""A schedule is read in a timezone of its own.

The default is the zone every schedule was read in before this column existed, so no row changes meaning.

Revision ID: 0011
Revises: 0010
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE schedules ADD COLUMN timezone text NOT NULL DEFAULT 'Europe/Warsaw'")


def downgrade() -> None:
    op.execute("ALTER TABLE schedules DROP COLUMN IF EXISTS timezone")
