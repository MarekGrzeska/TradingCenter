"""What a team learned, kept where the next run can read it — beside the revision rather than inside it. A
note in that immutable blob would mint a revision per note, and a team that learns by minting revisions can
never be run twice on the same one.

Keyed by team, so a memory outlives the run that wrote it. `author_agent_key` and `run_id` are legibility,
never permission. Rows are never updated: a correction is the next entry, so a trace read a week later
matches the memory the team actually had. The length ceiling is stated here too, being the only one of the
three whose breach would land on disk.

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Mirrors `teams.contract.MEMORY_ENTRY_MAX_CHARS`; `tests/teams/test_contract.py` reads
# both and fails when they differ.
_ENTRY_MAX_CHARS = 2000


def upgrade() -> None:
    op.create_table(
        "team_memories",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "team_id",
            sa.BigInteger(),
            sa.ForeignKey("teams.id", name="team_memories_team_id_fkey", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("author_agent_key", sa.Text(), nullable=False),
        sa.Column(
            "run_id",
            sa.BigInteger(),
            sa.ForeignKey("runs.id", name="team_memories_run_id_fkey", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            f"char_length(content) BETWEEN 1 AND {_ENTRY_MAX_CHARS}",
            name="team_memories_content_length",
        ),
    )
    # The one read there is: this team's entries, newest first, cut at the read ceiling.
    op.create_index(
        "team_memories_team_id_created_at_idx",
        "team_memories",
        ["team_id", sa.text("created_at DESC"), sa.text("id DESC")],
    )


def downgrade() -> None:
    op.drop_index("team_memories_team_id_created_at_idx", table_name="team_memories")
    op.drop_table("team_memories")
