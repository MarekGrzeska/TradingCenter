"""Makes `tool_calls` able to hold a call that was sent and never answered for: `message_id` becomes nullable, and
`outcome` gains `unknown`, the answer the model must not retry on. `downgrade` deletes those rows, which is a real loss.

Revision ID: 0011
Revises: 0010
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT = "tool_calls_outcome_known"
_OUTCOMES_BEFORE = ("ok", "refused", "unavailable")
_OUTCOMES_AFTER = (*_OUTCOMES_BEFORE, "unknown")


def _in_list(values: Sequence[str]) -> str:
    return "outcome IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def upgrade() -> None:
    op.alter_column("tool_calls", "message_id", existing_type=sa.BigInteger(), nullable=True)
    op.drop_constraint(_CONSTRAINT, "tool_calls", type_="check")
    op.create_check_constraint(_CONSTRAINT, "tool_calls", _in_list(_OUTCOMES_AFTER))


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM tool_calls WHERE message_id IS NULL OR outcome = 'unknown'"))
    op.drop_constraint(_CONSTRAINT, "tool_calls", type_="check")
    op.create_check_constraint(_CONSTRAINT, "tool_calls", _in_list(_OUTCOMES_BEFORE))
    op.alter_column("tool_calls", "message_id", existing_type=sa.BigInteger(), nullable=False)
