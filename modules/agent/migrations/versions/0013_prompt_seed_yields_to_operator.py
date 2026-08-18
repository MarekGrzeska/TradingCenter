"""Makes `prompt_revisions` able to say who wrote a row, so a seed can stop overwriting a person.

The bug this closes was reproduced, not inferred. Migrations seed `v4` through `v11`, each
one higher by one, and `_next_prompt_version` does the same `+1` from the latest — so the
version an operator gets by saving once is *always exactly* the one the next seeding
migration will use. With no unique on `version`, both rows went in, and
`latest_prompt_revision` is `ORDER BY id DESC`, so the seed won. `downgrade()` of a seeding
migration deletes `WHERE version = ...`, which at that point would have taken the operator's
text with it.

Three things, in an order that is load-bearing:

- **`source`**, because nothing in a row said where it came from, and the whole fix rests on
  telling the two apart.
- **the backfill**, derived rather than guessed. See `_SEEDED_VERSIONS` below.
- **de-duplication, then the unique.** Never the other way round: migrations here run inside
  `lifespan`, so a constraint that fails is not a red deploy, it is a module that will not
  start. By the time `create_unique_constraint` runs there is nothing left for it to refuse.

What this does *not* do is rewrite `0003`–`0012`. They are applied everywhere already, and
editing an applied migration is worse than the bug it would fix. The guard takes effect from
the next seeding migration, which uses `seed_prompt()` in `agent/prompt_seed.py`.

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

# Every version a migration has ever seeded: `0003` (v4), `0005`–`0010` (v5–v10) and
# `0012` (v11).
#
# Written out as literals rather than imported from those modules' `_SEED_VERSION`. This
# list describes the database as it stands the moment this migration runs, and it has to
# keep meaning that in a year, when those constants say something else or their files are
# gone. A backfill that reads today's code answers a different question every time it is
# replayed.
_SEEDED_VERSIONS = ("v4", "v5", "v6", "v7", "v8", "v9", "v10", "v11")


def upgrade() -> None:
    op.add_column(
        "prompt_revisions",
        # `operator` as the server default so the column is filled for every existing row
        # first and the backfill below only has to name the exceptions. New writes state
        # it explicitly anyway — `create_prompt_revision` does not rely on this.
        sa.Column("source", sa.Text(), nullable=False, server_default="operator"),
    )
    op.create_check_constraint(_CONSTRAINT, "prompt_revisions", "source IN ('seed', 'operator')")

    # A row is a seed exactly when a migration put it there, and that is recoverable:
    # its version is one a migration seeded, *and* it is the newest row carrying that
    # version. The second half is what handles a collision that already happened — two
    # rows named `v11` arise only one way, an operator's save followed by the seed, so
    # the later id is the migration's and the earlier one is the person's.
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

    # Anything still sharing a version with a seed is an operator's row that the seed
    # landed on top of. It keeps its text and its place in history and gives up only the
    # number, because the number is what `downgrade()` of a seeding migration aims at.
    # Renumbered rather than deleted: this is the one row in the table nobody can retype.
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
    # The renumbering is not undone. Reversing it would put two rows back under one
    # version — the state this migration exists to end — and the suffix is readable, which
    # a silently shadowed row was not.
    op.drop_constraint(_UNIQUE, "prompt_revisions", type_="unique")
    op.drop_constraint(_CONSTRAINT, "prompt_revisions", type_="check")
    op.drop_column("prompt_revisions", "source")
