"""Trades without a stop, each trade's result in % and its worst open loss, the close when the capital runs out, and the
deposit each instrument requires.

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

_REASONS = "'stop', 'target', 'trail', 'when', 'max_bars', 'end_of_range'"


def upgrade() -> None:
    op.execute("ALTER TABLE run_trades ALTER COLUMN initial_stop DROP NOT NULL, ALTER COLUMN result_r DROP NOT NULL")
    # Null for every trade recorded before engine version 3: a recorded result is never recomputed.
    op.execute("ALTER TABLE run_trades ADD COLUMN result_pct double precision, ADD COLUMN mae_pct double precision")
    op.execute("ALTER TABLE run_trades DROP CONSTRAINT run_trades_exit_reason_check")
    op.execute(
        f"ALTER TABLE run_trades ADD CONSTRAINT run_trades_exit_reason_check "
        f"CHECK (exit_reason IN ({_REASONS}, 'out_of_capital'))"
    )
    # Its own table rather than a column of `cost_profiles`: a run without costs, or with its own, may still be sized by
    # the deposit, and has no cost profile to hang it on.
    op.execute(
        """
        CREATE TABLE instrument_margins (
            symbol         text PRIMARY KEY,
            margin_factor  double precision NOT NULL CHECK (margin_factor > 0 AND margin_factor <= 1),
            source         text NOT NULL CHECK (source IN ('broker', 'operator')),
            broker         jsonb,
            updated_at     timestamptz NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE instrument_margins")
    op.execute(
        """
        DO $$
        DECLARE without_r bigint;
        BEGIN
            SELECT count(*) INTO without_r FROM run_trades WHERE result_r IS NULL OR exit_reason = 'out_of_capital';
            IF without_r > 0 THEN
                RAISE EXCEPTION '% trades have no stop or ran out of capital; engine 2 cannot hold them', without_r;
            END IF;
        END $$
        """
    )
    op.execute("ALTER TABLE run_trades DROP CONSTRAINT run_trades_exit_reason_check")
    op.execute(f"ALTER TABLE run_trades ADD CONSTRAINT run_trades_exit_reason_check CHECK (exit_reason IN ({_REASONS}))")
    op.execute("ALTER TABLE run_trades DROP COLUMN result_pct, DROP COLUMN mae_pct")
    op.execute("ALTER TABLE run_trades ALTER COLUMN initial_stop SET NOT NULL, ALTER COLUMN result_r SET NOT NULL")
