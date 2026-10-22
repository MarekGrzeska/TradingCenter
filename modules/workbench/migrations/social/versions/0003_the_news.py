"""The news: headlines from RSS feeds, each with the moments its delay is measured from, and what each
feed last did.

Kept apart from `posts` on purpose: a post is read by a model and may be announced, a headline is
neither yet, and a column set half of which is empty by design is two tables pretending to be one.

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
    # `first_seen_at` and `previous_fetch_at` are measurements, written once and never moved: the
    # delay's two bounds are computed from them on read. `previous_fetch_at IS NULL` is "found there".
    op.execute(
        """
        CREATE TABLE news_items (
            id                 bigserial PRIMARY KEY,
            source             text NOT NULL,
            external_id        text NOT NULL,
            publisher          text NOT NULL,
            title              text NOT NULL,
            summary            text NOT NULL DEFAULT '',
            url                text,
            published_at       timestamptz,
            first_seen_at      timestamptz NOT NULL,
            previous_fetch_at  timestamptz,
            kept_at            timestamptz,
            UNIQUE (source, external_id)
        )
        """
    )
    # The window every screen reads, ordered the way the contract promises.
    op.execute(
        "CREATE INDEX news_items_order_idx"
        " ON news_items ((COALESCE(published_at, first_seen_at)) DESC)"
    )
    # A source's day, for its latency figures — and the retention sweep, which walks the same column.
    op.execute("CREATE INDEX news_items_source_seen_idx ON news_items (source, first_seen_at)")
    op.execute("CREATE INDEX news_items_seen_idx ON news_items (first_seen_at)")
    op.execute("CREATE INDEX news_items_kept_idx ON news_items (kept_at) WHERE kept_at IS NOT NULL")

    op.execute(
        """
        CREATE TABLE news_sources (
            source               text PRIMARY KEY,
            last_attempt_at      timestamptz,
            last_success_at      timestamptz,
            last_failure_at      timestamptz,
            last_failure         text,
            newest_published_at  timestamptz
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE news_sources")
    op.execute("DROP TABLE news_items")
