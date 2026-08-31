"""One column: when the operator was told about a decision.

The gateway keeps no history of what it sent, so this is where deduplication has to stand — and it
is written only after a delivery succeeded, which makes it the retry as well as the marker.

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
    op.execute("ALTER TABLE decisions ADD COLUMN notified_at timestamptz")


def downgrade() -> None:
    op.execute("ALTER TABLE decisions DROP COLUMN notified_at")
