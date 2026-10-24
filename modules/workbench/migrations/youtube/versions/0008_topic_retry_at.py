"""A topic whose search the source refused waits its own interval before it is tried again. Its own column, not `last_run_at`:
that one is where the next search's window starts, and moving it on a failure would skip the films published meanwhile.

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE topics ADD COLUMN retry_at timestamptz")


def downgrade() -> None:
    op.execute("ALTER TABLE topics DROP COLUMN retry_at")
