"""A window of films is the films the archive found in it, so the window has an index of its own.

A channel's film is found hours after YouTube says it was published, and on a spent day two days after; a window on the
publication date showed an empty list on the morning the film was read.

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
    op.execute("CREATE INDEX videos_discovered_idx ON videos (discovered_at DESC)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS videos_discovered_idx")
