"""One index on `price_samples`, not two. `price_samples_outcome_time_idx` repeated the primary key's columns in
the same order, so every sample written maintained both — on a table of 2.9 GB by 23 September 2026 — and every
read could already be served by the key.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS price_samples_outcome_time_idx")


def downgrade() -> None:
    op.execute(
        "CREATE INDEX price_samples_outcome_time_idx ON price_samples (outcome_id, observed_at)"
    )
