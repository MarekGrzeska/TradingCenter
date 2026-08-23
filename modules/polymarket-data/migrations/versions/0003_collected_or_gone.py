"""An observation is collected or it is gone — the third state leaves the schema.

`tracking_ended_at` was the only thing that could produce an event which neither collects
nor leaves the list. Nothing sets it any more: the route that did is gone and so is the tool.
A column nothing writes, backing a state the contract still announces, is a promise with no
producer — so it goes too, rather than sitting there waiting for somebody to reach for it.

**The two steps are in the only order that works.** After the column is dropped there is no
way to tell which rows were the stopped ones, so they are deleted first. Their markets,
outcomes, samples and collected ranges go with them through the cascades already declared in
0001 and 0002 — the atomicity is the schema's, not this file's.

This deletes data the provider will not give back. It is the cost of two states instead of
three and it was taken deliberately (`openspec/changes/an-observation-is-collected-or-gone`).

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
    # Counted before the delete and logged at warning, the way `store.delete_history` logs
    # its own: a migration that quietly removed collected history would be the one thing
    # nobody could reconstruct afterwards, not even in principle.
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
    """The column comes back empty, and that is all a downgrade can honestly do.

    Every row it distinguished was deleted on the way up; there is nowhere to read them back
    from. A downgrade that silently produced an empty column while claiming to restore the
    state is the failure mode worth naming here rather than discovering.
    """
    op.execute("DROP INDEX IF EXISTS tracked_events_active_idx")
    op.execute("ALTER TABLE tracked_events ADD COLUMN tracking_ended_at timestamptz")
    op.execute(
        """
        CREATE INDEX tracked_events_active_idx ON tracked_events (id)
        WHERE tracking_ended_at IS NULL
        """
    )
