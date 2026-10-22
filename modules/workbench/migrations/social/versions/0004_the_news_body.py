"""The body of a headline where the feed carries one — the lead alone stays in `summary`.

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
    # Empty, not null: "the feed carried only a lead" is a normal state and a screen should not test for two kinds
    # of nothing. NOT NULL DEFAULT '' is a metadata-only change on PostgreSQL 11+, so no table rewrite.
    op.execute("ALTER TABLE news_items ADD COLUMN content text NOT NULL DEFAULT ''")


def downgrade() -> None:
    op.execute("ALTER TABLE news_items DROP COLUMN content")
