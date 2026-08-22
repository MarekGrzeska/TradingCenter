"""The platform's three tables: parameter sets, watches, and every decision made.

Revision ID: 0001
Revises:
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Append-only, and the append-only-ness is the point: a decision names the version it
    # was computed under, and that version has to still read the way it read then
    # (`strategy-catalogue`, "Decyzja zawsze niesie powód i pochodzenie"). Nothing updates
    # a row here; a change of mind is the next version.
    op.create_table(
        "parameter_sets",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        # The catalogue entry's id — text rather than a foreign key, because the
        # catalogue is code in the image, not a table. A row whose strategy has since
        # left the image is still readable, which is what a decision from that era needs.
        sa.Column("strategy_id", sa.Text, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("params", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("strategy_id", "version", name="parameter_sets_strategy_version"),
    )

    # One row per (strategy, symbol) the platform is watching. `active` is the whole of
    # the off switch: deactivating one MUST NOT touch the others
    # (`strategy-runtime`, "Platforma bez strategii jest stanem wspieranym").
    op.create_table(
        "watches",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("strategy_id", sa.Text, nullable=False),
        sa.Column("symbol", sa.Text, nullable=False),
        sa.Column(
            "parameter_set_id",
            sa.BigInteger,
            sa.ForeignKey("parameter_sets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("strategy_id", "symbol", name="watches_strategy_symbol"),
    )

    op.create_table(
        "decisions",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("strategy_id", sa.Text, nullable=False),
        sa.Column("symbol", sa.Text, nullable=False),
        sa.Column(
            "parameter_set_id",
            sa.BigInteger,
            sa.ForeignKey("parameter_sets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        # The closing time of the bar this decision was made on. Never the wall clock:
        # a decision belongs to a bar, and the same bar replayed must land on the same row
        # (`strategy-runtime`, "Każda ocena zostaje zapisana i daje się odtworzyć").
        sa.Column("as_of", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("reason", sa.Text, nullable=True),
        # Which layer refused. A refusal for want of data is answered by fetching history;
        # a refusal by the strategy is answered by reading the strategy — telling them
        # apart in the row is what keeps the two answers apart
        # (`strategy-runtime`, "Dziura w danych nie jest odpowiedzią").
        sa.Column("reason_kind", sa.Text, nullable=True),
        sa.Column("direction", sa.Text, nullable=True),
        sa.Column("entry", sa.Double, nullable=True),
        sa.Column("stop", sa.Double, nullable=True),
        sa.Column("target", sa.Double, nullable=True),
        sa.Column("rr", sa.Double, nullable=True),
        sa.Column("score", sa.Double, nullable=True),
        sa.Column("features", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        # The facts the decision stood on, in full. Not a pointer at the archive: replay
        # has to survive the archive's retention and any later correction to it
        # (design.md, decision 4).
        sa.Column("facts", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint("action in ('trade', 'no_trade')", name="decisions_action"),
        sa.CheckConstraint(
            "reason_kind is null or reason_kind in ('strategy', 'coverage', 'limit')",
            name="decisions_reason_kind",
        ),
        sa.CheckConstraint(
            "direction is null or direction in ('long', 'short')", name="decisions_direction"
        ),
        # A trade carries its levels or it is not a trade. Stated here as well as in the
        # dataclass, because a row is what a later reader actually has.
        sa.CheckConstraint(
            "action <> 'trade' or (direction is not null and entry is not null "
            "and stop is not null and target is not null)",
            name="decisions_trade_is_complete",
        ),
        # One decision per bar per watch. The loop is therefore idempotent: a restart that
        # re-reads the same closed bar writes nothing new (`runner/loop.py`).
        sa.UniqueConstraint("strategy_id", "symbol", "as_of", name="decisions_one_per_bar"),
    )
    # The tool surface's one hot query — the pending setups for a strategy, newest first.
    op.create_index(
        "decisions_pending",
        "decisions",
        ["strategy_id", "symbol", sa.text("as_of DESC")],
        postgresql_where=sa.text("action = 'trade'"),
    )


def downgrade() -> None:
    op.drop_index("decisions_pending", table_name="decisions")
    op.drop_table("decisions")
    op.drop_table("watches")
    op.drop_table("parameter_sets")
