"""The loop's interval and the topics' default limits become data the operator edits. One row at most: no row is the
process settings, which is why nothing is seeded — a seeded copy of an environment variable would freeze it.

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE loop_settings (
            id                     boolean PRIMARY KEY DEFAULT true CONSTRAINT loop_settings_is_one_row CHECK (id),
            poll_interval_minutes  integer NOT NULL CONSTRAINT loop_settings_poll_in_range CHECK (poll_interval_minutes BETWEEN 5 AND 1440),
            topic_interval_minutes integer NOT NULL CONSTRAINT loop_settings_topic_interval_in_range CHECK (topic_interval_minutes BETWEEN 15 AND 10080),
            topic_max_videos       integer NOT NULL CONSTRAINT loop_settings_topic_videos_in_range CHECK (topic_max_videos BETWEEN 1 AND 20),
            updated_at             timestamptz NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE loop_settings")
