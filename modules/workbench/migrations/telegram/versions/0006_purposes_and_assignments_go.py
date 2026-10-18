"""Who is told what is no longer decided here.

Assignments of purposes to destinations were converted into rules by the alerts package (`alerts-package`, the conversion
that ran at its first start, verified in production before this migration was merged), and the producers publish events to the rules instead of sending under a purpose. The two tables
are the last thing the door kept of a decision that is not its to make, and nothing reads them.

Not reversible in the data: `downgrade` brings back the empty tables, not the operator's assignments.

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
    op.execute("DROP TABLE assignments")
    op.execute("DROP TABLE purposes")


def downgrade() -> None:
    op.execute(
        """
        CREATE TABLE purposes (
            name         text PRIMARY KEY,
            description  text,
            first_seen   timestamptz NOT NULL DEFAULT now(),
            last_seen    timestamptz NOT NULL DEFAULT now(),
            last_caller  text
        )
        """
    )
    op.execute(
        """
        CREATE TABLE assignments (
            key            text PRIMARY KEY,
            destination_id bigint NOT NULL REFERENCES destinations(id) ON DELETE CASCADE,
            assigned_at    timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX assignments_destination_idx ON assignments (destination_id)")
