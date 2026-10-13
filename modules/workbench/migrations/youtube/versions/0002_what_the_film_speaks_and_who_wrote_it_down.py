"""What the film speaks and who wrote it down: `videos.audio_language`, so captions are asked for in the film's own
language and not in a translation, and `transcripts.model`, naming the model that listened when no captions did. The job
columns go: they waited for a provider answering by job, and the one that listens answers at once.

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
    op.execute("ALTER TABLE videos DROP COLUMN job_provider, DROP COLUMN job_id, ADD COLUMN audio_language text")
    op.execute("ALTER TABLE transcripts ADD COLUMN model text")


def downgrade() -> None:
    op.execute("ALTER TABLE transcripts DROP COLUMN model")
    op.execute("ALTER TABLE videos DROP COLUMN audio_language, ADD COLUMN job_provider text, ADD COLUMN job_id text")
