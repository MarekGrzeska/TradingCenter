"""The archive: observation groups, tracked events, their markets and outcomes, the price
samples, and the record of what has actually been collected.

Revision ID: 0001
Revises:
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A local category, deliberately not the provider's tag. A tag describes the public
    # database and is what `browse_events` filters on; a group describes what we watch.
    op.execute(
        """
        CREATE TABLE observation_groups (
            id          bigserial PRIMARY KEY,
            name        text NOT NULL UNIQUE,
            created_at  timestamptz NOT NULL DEFAULT now()
        )
        """
    )

    # `tracking_ended_at` rather than a DELETE: ending an observation stops the sampling and keeps
    # every sample, so the row survives as the anchor its markets, outcomes and samples hang from.
    op.execute(
        """
        CREATE TABLE tracked_events (
            id                 bigserial PRIMARY KEY,
            provider_event_id  text NOT NULL UNIQUE,
            slug               text NOT NULL,
            title              text NOT NULL,
            group_id           bigint REFERENCES observation_groups(id) ON DELETE SET NULL,
            tracked_at         timestamptz NOT NULL DEFAULT now(),
            tracking_ended_at  timestamptz,
            refreshed_at       timestamptz
        )
        """
    )
    op.execute("CREATE INDEX tracked_events_slug_idx ON tracked_events (slug)")
    op.execute(
        """
        CREATE INDEX tracked_events_active_idx ON tracked_events (id)
        WHERE tracking_ended_at IS NULL
        """
    )

    # An event holds one market or a hundred and twenty-eight of them, measured on one 2028 election
    # event. `resolved_outcome` stops the sampling; `closed` is the provider's flag, and they differ.
    op.execute(
        """
        CREATE TABLE markets (
            id                  bigserial PRIMARY KEY,
            event_id            bigint NOT NULL
                                REFERENCES tracked_events(id) ON DELETE CASCADE,
            provider_market_id  text NOT NULL UNIQUE,
            condition_id        text,
            question            text NOT NULL,
            group_item_title    text,
            neg_risk            boolean NOT NULL DEFAULT false,
            closed              boolean NOT NULL DEFAULT false,
            resolved_outcome    text,
            updated_at          timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX markets_event_idx ON markets (event_id)")

    # The outcome is what has a price, and a market may have more than two. `position` keeps the
    # provider's ordering, which pairs `outcomes[i]` with `clobTokenIds[i]`; both arrive as JSON in a string.
    op.execute(
        """
        CREATE TABLE outcomes (
            id                   bigserial PRIMARY KEY,
            market_id            bigint NOT NULL REFERENCES markets(id) ON DELETE CASCADE,
            position             integer NOT NULL,
            name                 text NOT NULL,
            token_id             text NOT NULL UNIQUE,
            oldest_available_at  timestamptz,
            UNIQUE (market_id, position)
        )
        """
    )

    # One row per (outcome, moment), whichever way the sample arrived; two valuations, because on a thin market they
    # differ by a lot. `quoted_at` is the moment the valuation is *about* — without it a stale trade reads as fresh.
    op.execute(
        """
        CREATE TABLE price_samples (
            outcome_id  bigint NOT NULL REFERENCES outcomes(id) ON DELETE CASCADE,
            observed_at timestamptz NOT NULL,
            midpoint    numeric(9, 6),
            last_trade  numeric(9, 6),
            quoted_at   timestamptz,
            source      text NOT NULL,
            PRIMARY KEY (outcome_id, observed_at),
            CONSTRAINT price_samples_have_a_price
                CHECK (midpoint IS NOT NULL OR last_trade IS NOT NULL),
            CONSTRAINT price_samples_are_probabilities
                CHECK (
                    (midpoint IS NULL OR (midpoint >= 0 AND midpoint <= 1))
                    AND (last_trade IS NULL OR (last_trade >= 0 AND last_trade <= 1))
                ),
            CONSTRAINT price_samples_name_their_surface
                CHECK (source IN ('gamma', 'clob'))
        )
        """
    )
    # The read every chart and every window computation makes: one outcome, ordered by time.
    op.execute(
        "CREATE INDEX price_samples_outcome_time_idx ON price_samples (outcome_id, observed_at)"
    )

    # What has actually been collected, as opposed to what happens to have rows. No sample because
    # nobody traded and no sample because the module was down look identical without this table.
    op.execute(
        """
        CREATE TABLE collected_ranges (
            id          bigserial PRIMARY KEY,
            outcome_id  bigint NOT NULL REFERENCES outcomes(id) ON DELETE CASCADE,
            starts_at   timestamptz NOT NULL,
            ends_at     timestamptz NOT NULL,
            CONSTRAINT collected_ranges_are_forward CHECK (ends_at >= starts_at)
        )
        """
    )
    op.execute(
        "CREATE INDEX collected_ranges_outcome_idx ON collected_ranges (outcome_id, starts_at)"
    )


def downgrade() -> None:
    # Reverse order of creation: every drop below is a table something above it references.
    op.execute("DROP TABLE collected_ranges")
    op.execute("DROP TABLE price_samples")
    op.execute("DROP TABLE outcomes")
    op.execute("DROP TABLE markets")
    op.execute("DROP TABLE tracked_events")
    op.execute("DROP TABLE observation_groups")
