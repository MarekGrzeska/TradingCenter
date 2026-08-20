"""Adds `stopped` to `messages` — whether this reply ended because the operator said so.

`incomplete` already says "this is not the whole answer", and that stays true for a reply
the operator cut off. What it cannot say is *who* cut it, and the two readings lead
somewhere different: a model that broke is something to retry, and an operator who
stopped is something they meant (specs/agent-chat, "Zatrzymana odróżnia się od urwanej
błędem").

A column beside `incomplete` rather than one replacing both with an ending enum: the enum
is tidier on a blank page, but it rewrites the meaning of every row already written and
changes a contract the terminal already reads (design.md, D4). `not null default false`
means every reply standing today comes out of this migration as what it was — not stopped.

The check constraint is recreated rather than added beside: an operator's message carries
neither flag, and that rule was already spelled once in `0001`. Two constraints saying
half of it each would be two places to keep in step.

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
