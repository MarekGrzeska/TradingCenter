"""A trade names the account it went to.

Null is the active account, which is where every trade before this column went.

Revision ID: 0012
Revises: 0011
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE trades ADD COLUMN account_id text")


def downgrade() -> None:
    op.execute("ALTER TABLE trades DROP COLUMN IF EXISTS account_id")
