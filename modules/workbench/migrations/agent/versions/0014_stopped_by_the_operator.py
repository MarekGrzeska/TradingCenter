"""Adds `stopped` to `messages` — whether this reply ended because the operator said so. `incomplete`
cannot say *who* cut it, and a model that broke is something to retry where an operator meant it.

A column beside `incomplete` rather than an ending enum replacing both: the enum is tidier on a blank page
and rewrites the meaning of every row already written. The check constraint is recreated rather than
added beside, or the one rule would be spelled in two places.

Revision ID: 0014
Revises: 0013
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT = "messages_model_fields_match_role"

_WITHOUT_STOPPED = (
    "(role = 'operator' AND model_id IS NULL AND prompt_version IS NULL "
    "AND incomplete = false) OR "
    "(role = 'agent' AND model_id IS NOT NULL AND prompt_version IS NOT NULL)"
)

_WITH_STOPPED = (
    "(role = 'operator' AND model_id IS NULL AND prompt_version IS NULL "
    "AND incomplete = false AND stopped = false) OR "
    "(role = 'agent' AND model_id IS NOT NULL AND prompt_version IS NOT NULL)"
)


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("stopped", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.drop_constraint(_CONSTRAINT, "messages", type_="check")
    op.create_check_constraint(_CONSTRAINT, "messages", _WITH_STOPPED)


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "messages", type_="check")
    op.create_check_constraint(_CONSTRAINT, "messages", _WITHOUT_STOPPED)
    op.drop_column("messages", "stopped")
