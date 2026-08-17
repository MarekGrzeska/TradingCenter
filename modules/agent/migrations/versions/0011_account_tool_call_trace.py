"""Makes `tool_calls` able to hold a call that was sent and never answered for.

Two changes, and they are the same change seen from two sides:

- **`message_id` becomes nullable.** Until now a tool call could only be written after
  the agent's reply existed, because the column pointed at it and was `NOT NULL` — the
  comment in `0002` says so outright. That is fine for a call that reads the archive: an
  odczyt that vanished with its turn cost nothing. It is not fine for a call that moves
  the account, which must leave its row *before* it is sent, when there is no reply to
  point at yet (specs/agent-trading, "Wywołanie ruszające rachunek zostawia ślad przed
  wysłaniem"). A turn that reaches its reply fills the column in on the way out, so a
  `NULL` here means exactly one thing: the turn died between sending and answering.
- **`outcome` gains `unknown`.** `unavailable` means the server never answered and
  nothing happened — the sentence this module has been writing for a failed odczyt. For
  an order it would be a claim nobody can make. `unknown` is the fourth answer, and it is
  the one the model must not retry on.

No new index. Osierocone rows are read by `session_id`, which `ix_tool_calls_session_id`
already covers, and `ix_tool_calls_message` takes a `NULL` without complaint.

`downgrade` cannot restore `NOT NULL` while an unanswered call is in the table, so it
deletes those rows first. That is a real loss — it is the record of an order whose fate is
unknown — which is why it is in `downgrade` and not anywhere else.

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
