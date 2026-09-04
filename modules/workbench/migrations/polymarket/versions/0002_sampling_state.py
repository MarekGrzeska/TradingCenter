"""What collection is currently doing, per tracked event. A failure that lives only in a log is a
failure nobody reads: silence in the data would otherwise read exactly like silence in the market.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE sampling_state (
            event_id              bigint PRIMARY KEY
                                  REFERENCES tracked_events(id) ON DELETE CASCADE,
            last_success_at       timestamptz,
            last_failure_at       timestamptz,
            last_failure_reason   text,
            consecutive_failures  integer NOT NULL DEFAULT 0
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE sampling_state")
