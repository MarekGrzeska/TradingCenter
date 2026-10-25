"""The costs the operator sets for an instrument, who asked for each run, and each run's headline numbers.

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
    # One profile per instrument, replaced rather than versioned: a run copies the values it used into its `request`, so
    # the history of what a run cost lives with the run.
    op.execute(
        """
        CREATE TABLE cost_profiles (
            symbol      text PRIMARY KEY,
            costs       jsonb NOT NULL,
            updated_at  timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    # Every run before this one was asked for over REST, which only the operator reaches.
    op.execute(
        "ALTER TABLE runs ADD COLUMN requested_by text NOT NULL DEFAULT 'operator' "
        "CHECK (requested_by IN ('operator', 'agent'))"
    )
    # The five numbers a list of runs shows, beside the report rather than read out of it: a report carries the daily
    # curve, and a list polled every few seconds while a run computes would detoast every one of them each time.
    op.execute("ALTER TABLE runs ADD COLUMN headline jsonb")
    op.execute(
        """
        UPDATE runs SET headline = jsonb_build_object(
            'trades', report->'trades', 'total_r', report->'total_r', 'expectancy_r', report->'expectancy_r',
            'max_drawdown_r', report->'max_drawdown_r', 'sharpe', report->'sharpe')
        WHERE report IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE runs DROP COLUMN headline")
    op.execute("ALTER TABLE runs DROP COLUMN requested_by")
    op.execute("DROP TABLE cost_profiles")
