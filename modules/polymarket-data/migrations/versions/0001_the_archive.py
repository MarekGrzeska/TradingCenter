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

    # `tracking_ended_at` rather than a DELETE: ending an observation stops the sampling and
    # keeps every sample already collected, so the row has to survive as the anchor its
    # markets, outcomes and samples hang from. Tracking the same event again clears it, and
    # the history is still there to be continued rather than restarted.
    #
    # `ON DELETE SET NULL` for the group: deleting a group must not delete observations.
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

    # An event holds one market or a hundred and twenty-eight of them — measured on a
    # single 2028 election event. `resolved_outcome` names which outcome won, and is what
    # stops the sampling for this market; `closed` is the provider's own flag, kept beside
    # it because the two do not always arrive together.
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

    # The outcome is what has a price, and a market may have more than two of them. The
    # source application stored a sample only where the outcomes were exactly Yes and No,
    # and everything else vanished without a line in a log.
    #
    # `position` keeps the provider's own ordering, which is what pairs `outcomes[i]` with
    # `clobTokenIds[i]` in its response — both arrive as JSON inside a string, and are
    # parsed once here rather than at every use.
    #
    # `oldest_available_at` is the "the provider has nothing older" boundary. It is written
    # at the oldest point a read actually returned, never at the edge of the window asked
    # for: those two are separated by everything the provider did not have, and writing the
    # second announces as checked something nobody checked.
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

    # One row per (outcome, moment), whichever way the sample arrived — the sampler and the
    # backfill meet in the same minute often, and two rows for one moment would leave a
    # series with two prices at one instant and no way to say which is the archive's answer.
    #
    # Two valuations, two columns, at least one of them present. They answer different
    # questions and on a thin market they differ by a lot: measured 22 August 2026 on one,
    # last trade 0.003 against a 0.002/0.004 book. `source` records which provider surface
    # the row came from, because the whole saving in the sampler rests on the metadata
    # surface publishing the same midpoint the order book does — a fact that is measured and
    # therefore has to stay checkable.
    #
    # `quoted_at` is the moment the valuation itself is *about*, when the provider says so.
    # Without it a price from a trade nine hours ago is indistinguishable from one a minute
    # old.
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

    # What has actually been collected, as opposed to what happens to have rows in it. No
    # sample at 3 a.m. because nobody traded and no sample because the module was not
    # running look identical in `price_samples`, and only this table tells them apart.
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
