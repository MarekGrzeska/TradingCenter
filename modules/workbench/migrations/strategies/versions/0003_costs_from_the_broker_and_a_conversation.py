"""Where a cost profile came from, and the conversation a strategy is written in.

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
    # Every profile before this one was typed by the operator. `broker` keeps the provider's own numbers beside the
    # converted ones, so a misread sign or unit can be seen in the row rather than inferred from results.
    op.execute(
        "ALTER TABLE cost_profiles ADD COLUMN source text NOT NULL DEFAULT 'operator' "
        "CHECK (source IN ('operator', 'broker'))"
    )
    op.execute("ALTER TABLE cost_profiles ADD COLUMN fetched_at timestamptz")
    op.execute("ALTER TABLE cost_profiles ADD COLUMN broker jsonb")
    # An id in the conversation's own schema, never a foreign key: this package does not read it, and a deleted
    # conversation only means the window starts a new one.
    op.execute("ALTER TABLE strategies ADD COLUMN conversation_id bigint")


def downgrade() -> None:
    op.execute("ALTER TABLE strategies DROP COLUMN conversation_id")
    op.execute("ALTER TABLE cost_profiles DROP COLUMN broker")
    op.execute("ALTER TABLE cost_profiles DROP COLUMN fetched_at")
    op.execute("ALTER TABLE cost_profiles DROP COLUMN source")
