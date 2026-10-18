"""Purposes and who receives them. A purpose is an open dotted name a producer sends under; an assignment
says which destination a purpose — or a prefix of one, or everything — goes to.

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
    op.execute(
        """
        CREATE TABLE purposes (
            -- Open: a producer may invent one at the moment it sends, so this table is a record of what
            -- has been seen or announced, never a list of what is allowed.
            name         text PRIMARY KEY,
            description  text,
            first_seen   timestamptz NOT NULL DEFAULT now(),
            last_seen    timestamptz NOT NULL DEFAULT now(),
            last_caller  text
        )
        """
    )
    op.execute(
        """
        CREATE TABLE assignments (
            -- A purpose, a prefix of one (matched on whole segments), or '*'. One key, one destination:
            -- the primary key is what makes "a purpose has at most one recipient" true.
            key            text PRIMARY KEY,
            -- RESTRICT, not CASCADE: a destination that is still somebody's recipient must not vanish
            -- with the alerts silently going nowhere. The routes refuse first and name the keys; this
            -- is what holds when a route forgets.
            destination_id bigint NOT NULL REFERENCES destinations(id) ON DELETE RESTRICT,
            assigned_at    timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX assignments_destination_idx ON assignments (destination_id)")


def downgrade() -> None:
    op.execute("DROP TABLE assignments")
    op.execute("DROP TABLE purposes")
