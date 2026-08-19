"""Where the operator put each agent on the canvas.

Beside the revision, deliberately not inside it. A definition is immutable once saved and
is what a run points at (specs/teams-catalogue, "Rewizja raz zapisana się nie zmienia"),
so coordinates living in that JSONB would mint a revision every time a node was dragged —
and a catalogue where "v7 vs v8" is sometimes a different team and sometimes the same one
moved sideways answers none of the questions it exists for. This table is mutable, keyed by
team and agent key, and overwritten in place (specs/terminal-teams, "Rozmieszczenie agentów
jest wyborem operatora i przeżywa zamknięcie widoku").

One consequence, accepted: a layout belongs to the team, not to a revision, so it is shared
by all of them. An agent the layout does not know — added since the last drag, or present
only in the older revision a run is being watched on — gets a place computed from the
dependencies instead. The layout is a remembered hint, never a claim about where something
is.

`agent_key` is the definition's own key rather than a foreign key to anything: agents are
JSONB inside a revision, not rows, and a key that disappears from every revision simply
leaves a row nobody reads.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "team_layouts",
        sa.Column(
            "team_id",
            sa.BigInteger(),
            sa.ForeignKey("teams.id", name="team_layouts_team_id_fkey", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_key", sa.Text(), nullable=False),
        # Canvas coordinates as the browser reports them — negative on both axes is
        # ordinary, and a double is what React Flow hands back after a zoomed drag.
        sa.Column("x", sa.Double(), nullable=False),
        sa.Column("y", sa.Double(), nullable=False),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # One place per agent per team: the write is an upsert onto this key, which is why
        # dragging the same node twice leaves one row rather than a history nobody reads.
        sa.PrimaryKeyConstraint("team_id", "agent_key", name="team_layouts_pkey"),
    )


def downgrade() -> None:
    op.drop_table("team_layouts")
