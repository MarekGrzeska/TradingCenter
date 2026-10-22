"""A finished run is something the alerts package can be told about, once.

`announced_at` is the marker of having told it: set after the alerts package has accepted the run, so a refusal leaves the
run to be tried again — the one retry this system has. Runs that finished before this column existed are marked as told,
at the moment they finished: the first deploy must not announce a backlog.

Revision ID: 0010
Revises: 0009
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE runs ADD COLUMN announced_at timestamptz")
    op.execute(
        "UPDATE runs SET announced_at = finished_at WHERE status IN ('completed', 'failed', 'cancelled')"
    )
    # Exactly the runs still to be told, so the sweep reads them and nothing else.
    op.execute(
        """
        CREATE INDEX ix_runs_unannounced ON runs (finished_at)
         WHERE announced_at IS NULL AND status IN ('completed', 'failed', 'cancelled')
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_runs_unannounced")
    op.execute("ALTER TABLE runs DROP COLUMN IF EXISTS announced_at")
