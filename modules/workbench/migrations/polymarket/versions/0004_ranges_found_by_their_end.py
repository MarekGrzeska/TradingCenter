"""A collected range is found by its end. Merging a new window asks which ranges end at or after its
start, and on `(outcome_id, starts_at)` that read every range the outcome ever had: 47 s for one event
on 23 September 2026, with 21 000 unmerged tick ranges per outcome. On the end it is the last few.

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
        "CREATE INDEX IF NOT EXISTS collected_ranges_outcome_end_idx "
        "ON collected_ranges (outcome_id, ends_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS collected_ranges_outcome_end_idx")
