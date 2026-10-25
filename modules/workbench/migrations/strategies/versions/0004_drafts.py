"""The agent's drafts: a document put into the operator's editor without a revision.

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
    # One row per place a draft can stand: a strategy, or — `strategy_id` null — the new one not saved yet. `seq` is how
    # the terminal tells a draft it has shown from the next one, which can carry the same document.
    op.execute(
        """
        CREATE TABLE strategy_drafts (
            strategy_id bigint REFERENCES strategies (id),
            document    jsonb NOT NULL,
            seq         bigint GENERATED ALWAYS AS IDENTITY,
            updated_at  timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX strategy_drafts_place ON strategy_drafts (coalesce(strategy_id, 0))")


def downgrade() -> None:
    op.execute("DROP TABLE strategy_drafts")
