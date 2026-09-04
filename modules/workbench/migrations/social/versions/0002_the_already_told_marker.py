"""One column: when this archive told the operator about a post.

The gateway keeps no history of what it sent, so deduplication has to stand somewhere — and this is
the somewhere. It is also the whole retry mechanism: the marker is written only after a delivery
succeeded, so a failed one leaves the post waiting for the next pass.

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
    op.execute("ALTER TABLE posts ADD COLUMN notified_at timestamptz")
    # The question the alert pass asks every round: unannounced posts, worst case the whole archive.
    # Partial, because a post that has been announced is never a candidate again.
    op.execute(
        """
        CREATE INDEX posts_awaiting_notification_idx
            ON posts (impact_score DESC, published_at DESC)
            WHERE notified_at IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX posts_awaiting_notification_idx")
    op.execute("ALTER TABLE posts DROP COLUMN notified_at")
