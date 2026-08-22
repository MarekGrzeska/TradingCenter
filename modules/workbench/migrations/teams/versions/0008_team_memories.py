"""What a team learned, kept where the next run can read it.

Beside the revision rather than inside it, for the same reason `team_layouts` is
(migration 0004) and one more. The shared reason: a definition is immutable once saved
and is what a run points at, so a note written into that JSONB would mint a revision per
note. The extra one is the whole point of the feature — two runs of the same revision are
comparable *because* the revision did not move between them, and a team that learns by
minting revisions can never be run twice on the same one.

Keyed by team, so the memory outlives both the run that wrote it and the revision that
was current at the time (specs/teams-memory, "Pamięć należy do zespołu i przeżywa
przebieg"). The owner is reached by joining `teams`, which is what keeps the owner filter
inside every statement rather than in a route that could forget it.

`author_agent_key` and `run_id` are legibility, never permission: nothing decides who may
read an entry from either of them. `run_id` is nullable and `ON DELETE SET NULL` — an
entry that outlives its run is still true, and the column leaves room for an entry the
operator writes by hand, which this change does not add.

Rows are never updated. A correction is the next entry (specs/teams-memory, "Wpis raz
zapisany się nie zmienia"), so a run's trace read a week later matches the memory the team
actually had, not the memory it has now. Only the operator deletes, one entry at a time,
through a route — no tool handed to an agent removes anything.

The length ceiling is stated here as well as in the module because it is the only one of
the three whose breach would land on disk. `MEMORY_ENTRY_MAX_CHARS` in `teams/contract.py`
is the same number, and a test fails when the two drift apart.

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
