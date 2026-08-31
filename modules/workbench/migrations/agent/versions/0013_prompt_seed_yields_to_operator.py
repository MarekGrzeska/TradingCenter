"""Makes `prompt_revisions` able to say who wrote a row, so a seed stops overwriting a person — reproduced, not
inferred. Three steps in a load-bearing order: the column, a derived backfill, de-duplication before the unique.

Revision ID: 0013
Revises: 0012
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT = "prompt_revisions_source_known"
_UNIQUE = "prompt_revisions_version_unique"

# Every version a migration has ever seeded. Written out as literals rather than imported: this list
# describes the database as it stands the moment this runs, and has to keep meaning that in a year.
_SEEDED_VERSIONS = ("v4", "v5", "v6", "v7", "v8", "v9", "v10", "v11")


def upgrade() -> None:
    op.add_column(
        "prompt_revisions",
        # `operator` as the server default so the column is filled for every existing row first and the
        # backfill below only names the exceptions. New writes state it explicitly anyway.
        sa.Column("source", sa.Text(), nullable=False, server_default="operator"),
    )
    op.create_check_constraint(_CONSTRAINT, "prompt_revisions", "source IN ('seed', 'operator')")

    # A row is a seed exactly when a migration put it there, and that is recoverable: its version is one
    # a migration seeded, *and* it is the newest row carrying that version.
    op.execute(
        sa.text(
            """
            UPDATE prompt_revisions SET source = 'seed'
             WHERE version = ANY(:seeded)
               AND id = (
                   SELECT max(same_version.id) FROM prompt_revisions AS same_version
                    WHERE same_version.version = prompt_revisions.version
               )
            """
        ).bindparams(sa.bindparam("seeded", value=list(_SEEDED_VERSIONS), type_=sa.ARRAY(sa.Text)))
    )

    # Anything still sharing a version with a seed is an operator's row the seed landed on top of. It
    # gives up only the number — renumbered rather than deleted, being the one row nobody can retype.
    op.execute(
        sa.text(
            """
            UPDATE prompt_revisions
               SET version = version || '+operator' || id::text
             WHERE source = 'operator'
               AND version IN (SELECT version FROM prompt_revisions WHERE source = 'seed')
            """
        )
    )

    op.create_unique_constraint(_UNIQUE, "prompt_revisions", ["version"])


def downgrade() -> None:
    # The renumbering is not undone. Reversing it would put two rows back under one version, which is the
    # state this migration exists to end.
    op.drop_constraint(_UNIQUE, "prompt_revisions", type_="unique")
    op.drop_constraint(_CONSTRAINT, "prompt_revisions", type_="check")
    op.drop_column("prompt_revisions", "source")
