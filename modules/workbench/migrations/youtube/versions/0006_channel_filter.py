"""A channel may carry a filter, and a film that did not pass it is kept as `filtered_out` with the reason. Kept, not dropped:
a row is what stops the next pass paying to judge the same film again. Channels get NULL, which is how they behaved before.

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
    op.execute(
        "ALTER TABLE channels ADD COLUMN filter text "
        "CONSTRAINT channels_filter_in_range CHECK (filter IS NULL OR char_length(filter) BETWEEN 1 AND 1000)"
    )
    op.execute("ALTER TABLE videos DROP CONSTRAINT videos_state_is_known")
    op.execute(
        """
        ALTER TABLE videos ADD CONSTRAINT videos_state_is_known CHECK (state IN (
            'discovered', 'no_transcript', 'transcribed', 'analysed',
            'notified', 'quiet', 'gave_up', 'skipped', 'filtered_out'
        ))
        """
    )
    # A film the filter turned away that does not say why is one nobody can overrule with open eyes.
    op.execute(
        "ALTER TABLE videos ADD CONSTRAINT videos_filtered_says_why "
        "CHECK (state <> 'filtered_out' OR skip_reason IS NOT NULL)"
    )


def downgrade() -> None:
    # They were never read, so they come back as new films the next time their channel lists them.
    op.execute("DELETE FROM videos WHERE state = 'filtered_out'")
    op.execute("ALTER TABLE videos DROP CONSTRAINT videos_filtered_says_why")
    op.execute("ALTER TABLE videos DROP CONSTRAINT videos_state_is_known")
    op.execute(
        """
        ALTER TABLE videos ADD CONSTRAINT videos_state_is_known CHECK (state IN (
            'discovered', 'no_transcript', 'transcribed', 'analysed',
            'notified', 'quiet', 'gave_up', 'skipped'
        ))
        """
    )
    op.execute("ALTER TABLE channels DROP COLUMN filter")
