"""An observation is collected or it is gone: a column nothing writes, backing a state the contract announces, is a
promise with no producer. The rows go before the column, since afterwards there is no telling which they were.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

log = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    # Counted before the delete and logged at warning, the way `store.delete_history` logs its own: a
    # migration that quietly removed collected history is the one thing nobody could reconstruct.
    gone = op.get_bind().scalar(
        sa.text("SELECT count(*) FROM tracked_events WHERE tracking_ended_at IS NOT NULL")
    )
    log.warning(
        "removing %s observation(s) stopped before this revision, with everything collected "
        "for them",
        gone,
    )
    op.execute("DELETE FROM tracked_events WHERE tracking_ended_at IS NOT NULL")

    # The partial index is defined on the column, so it goes with it.
    op.execute("DROP INDEX IF EXISTS tracked_events_active_idx")
    op.execute("ALTER TABLE tracked_events DROP COLUMN tracking_ended_at")
    op.execute("CREATE INDEX IF NOT EXISTS tracked_events_active_idx ON tracked_events (id)")


def downgrade() -> None:
    """The column comes back empty, and that is all a downgrade can honestly do: every row it
    distinguished was deleted on the way up, and there is nowhere to read them back from."""
    op.execute("DROP INDEX IF EXISTS tracked_events_active_idx")
    op.execute("ALTER TABLE tracked_events ADD COLUMN tracking_ended_at timestamptz")
    op.execute(
        """
        CREATE INDEX tracked_events_active_idx ON tracked_events (id)
        WHERE tracking_ended_at IS NULL
        """
    )
