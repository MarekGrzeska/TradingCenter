"""The account that owns the bots: one row, and the session in it encrypted. The key is in the process's
environment and never here — a dump of this table alone opens nothing.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE account_session (
            -- One account at a time. The constraint is the rule: a second login replaces the first.
            id                int PRIMARY KEY CHECK (id = 1),
            session_encrypted text NOT NULL,
            username          text NOT NULL,
            -- Masked before it is stored: nothing here needs the whole number.
            phone_masked      text NOT NULL,
            logged_in_at      timestamptz NOT NULL DEFAULT now(),
            -- Set when Telegram refused the session at the moment it was used, e.g. ended from the phone.
            rejected_at       timestamptz
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE account_session")
