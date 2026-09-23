"""One group per spelling. `UNIQUE (name)` let "Crypto" and "crypto " stand side by side, and models asked for both;
the index now sits on the name lower-cased with its whitespace collapsed. Duplicates already there are merged into
the oldest of each spelling before the index can be built — their events move, nothing else is touched.

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

# `store._name_key('name')`, copied rather than imported: a migration is a snapshot of the schema it made.
_KEY = "lower(btrim(regexp_replace(name, '[[:space:]]+', ' ', 'g')))"


def upgrade() -> None:
    op.execute(
        f"""
        WITH keyed AS (
            SELECT id, min(id) OVER (PARTITION BY {_KEY}) AS keeper FROM observation_groups
        )
        UPDATE tracked_events e SET group_id = keyed.keeper
        FROM keyed WHERE e.group_id = keyed.id AND keyed.id <> keyed.keeper
        """
    )
    op.execute(
        f"""
        DELETE FROM observation_groups g
        USING (SELECT id, min(id) OVER (PARTITION BY {_KEY}) AS keeper FROM observation_groups) keyed
        WHERE g.id = keyed.id AND keyed.id <> keyed.keeper
        """
    )
    op.execute("ALTER TABLE observation_groups DROP CONSTRAINT IF EXISTS observation_groups_name_key")
    op.execute(f"CREATE UNIQUE INDEX observation_groups_name_key_idx ON observation_groups (({_KEY}))")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS observation_groups_name_key_idx")
    op.execute(
        "ALTER TABLE observation_groups ADD CONSTRAINT observation_groups_name_key UNIQUE (name)"
    )
