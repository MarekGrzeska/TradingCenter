"""Usage found by its date. Every run start sums the team's cost since the day began, and with no index on the
date that sum read the team's whole history — the shape of #263 and #264, still small here. `trades` has had
its own since 0006.

Revision ID: 0009
Revises: 0008
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_usage_created_at", "usage", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_usage_created_at", table_name="usage")
