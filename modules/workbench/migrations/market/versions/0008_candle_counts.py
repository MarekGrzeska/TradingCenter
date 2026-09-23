"""How many candles each pair holds, kept rather than counted. Counting them read the whole table on every
status read — the gauge each minute, the terminal every 15 s — and at 1,1M candles that was 48 s on a
throttled server (23 September 2026), linear in the archive's depth.

Kept by statement-level triggers rather than by `write_candles`: during a deployment the previous image
still writes candles, and a counter only the new code maintained would drift by whatever it wrote.
The transition tables hold only the rows a statement actually inserted or deleted, so an upsert that
updated an existing period changes nothing.

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE candle_counts (
            symbol      text   NOT NULL,
            resolution  text   NOT NULL,
            candles     bigint NOT NULL CHECK (candles >= 0),
            PRIMARY KEY (symbol, resolution)
        )
        """
    )
    op.execute(
        """
        CREATE FUNCTION candle_counts_add() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            -- Ordered by the key, so two statements touching the same pairs lock them in one order.
            INSERT INTO candle_counts (symbol, resolution, candles)
            SELECT symbol, resolution, count(*) FROM inserted
             GROUP BY symbol, resolution ORDER BY symbol, resolution
            ON CONFLICT (symbol, resolution)
            DO UPDATE SET candles = candle_counts.candles + EXCLUDED.candles;
            RETURN NULL;
        END $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION candle_counts_remove() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            UPDATE candle_counts c SET candles = c.candles - d.n
              FROM (SELECT symbol, resolution, count(*) AS n FROM deleted
                     GROUP BY symbol, resolution ORDER BY symbol, resolution) d
             WHERE c.symbol = d.symbol AND c.resolution = d.resolution;
            RETURN NULL;
        END $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION candle_counts_clear() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            DELETE FROM candle_counts;
            RETURN NULL;
        END $$
        """
    )

    # The count and the triggers under one lock: a candle written between the two would be in the
    # table and in neither the starting count nor a trigger's.
    op.execute("LOCK TABLE candles IN SHARE MODE")
    op.execute(
        """
        INSERT INTO candle_counts (symbol, resolution, candles)
        SELECT symbol, resolution, count(*) FROM candles GROUP BY symbol, resolution
        """
    )
    op.execute(
        """
        CREATE TRIGGER candle_counts_on_insert AFTER INSERT ON candles
        REFERENCING NEW TABLE AS inserted
        FOR EACH STATEMENT EXECUTE FUNCTION candle_counts_add()
        """
    )
    op.execute(
        """
        CREATE TRIGGER candle_counts_on_delete AFTER DELETE ON candles
        REFERENCING OLD TABLE AS deleted
        FOR EACH STATEMENT EXECUTE FUNCTION candle_counts_remove()
        """
    )
    # TRUNCATE fires no DELETE trigger, and is what the test suite and an operator's reset use.
    op.execute(
        """
        CREATE TRIGGER candle_counts_on_truncate AFTER TRUNCATE ON candles
        FOR EACH STATEMENT EXECUTE FUNCTION candle_counts_clear()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS candle_counts_on_truncate ON candles")
    op.execute("DROP TRIGGER IF EXISTS candle_counts_on_delete ON candles")
    op.execute("DROP TRIGGER IF EXISTS candle_counts_on_insert ON candles")
    op.execute("DROP FUNCTION IF EXISTS candle_counts_clear()")
    op.execute("DROP FUNCTION IF EXISTS candle_counts_remove()")
    op.execute("DROP FUNCTION IF EXISTS candle_counts_add()")
    op.execute("DROP TABLE IF EXISTS candle_counts")
