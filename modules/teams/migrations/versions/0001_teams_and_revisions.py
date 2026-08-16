"""The catalogue: named teams, and the append-only revisions of their definitions.

A team is a position in the catalogue — name, description, who owns it, when it last
changed. `team_revisions` holds the thing that actually gets run: one JSONB blob per
version, carrying every agent's role, prompt, wytyczne, model and assigned tools, and
every dependency between them (specs/teams-catalogue, "Definicja zespołu wystarcza, żeby
zbudować z niej pracę"). A row here is never updated once written — a fresh save inserts
the next version rather than touching an earlier one, which is what lets a run point at
exactly the definition it ran on (specs/teams-catalogue, "Rewizja raz zapisana się nie
zmienia").

`archived_at` retires a team from the list an operator picks a run from without
deleting it: `runs` will reference a revision, not a team, so wiping a team's history
along with it would throw away exactly the experiment results this module exists to keep
(specs/teams-catalogue, "Zespół wycofany z katalogu nie zabiera ze sobą przebiegów").

No validation of `definition`'s shape lives here — acyclicity, reachability, and every
agent naming a model and tools that actually exist are checked in the application before
a revision is ever inserted (specs/teams-catalogue, "Definicja, której nie da się
wykonać, jest odrzucana przy zapisie"). A CHECK constraint has no way to look up the
model catalogue or the tool server's own announcement, so the row itself only enforces
what needs no context: that a revision belongs to a team and carries some definition.

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
    op.create_table(
        "teams",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        # Who created this team — the Easy Auth principal, or the constant "anonymous"
        # identity a module started without REQUIRE_AUTHENTICATED_PRINCIPAL assigns
        # (specs/teams-browser-access). Every read is filtered by this.
        sa.Column("owner_principal", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        # Set when the operator retires a team from the catalogue. A stamp rather than a
        # `DELETE` — see this file's own docstring for why: runs and the revisions they
        # point at MUST stay readable.
        sa.Column("archived_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # Bumped by the application whenever a new revision is saved — "moment ostatniej
        # zmiany" in the catalogue listing (specs/teams-catalogue, "Katalog wystarcza,
        # żeby wybrać zespół bez otwierania go"). Not derived from `team_revisions` at
        # read time so the catalogue list stays a single-table query.
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_teams_owner_updated",
        "teams",
        ["owner_principal", sa.text("updated_at DESC")],
    )

    op.create_table(
        "team_revisions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "team_id",
            sa.BigInteger(),
            sa.ForeignKey("teams.id", name="team_revisions_team_id_fkey"),
            nullable=False,
        ),
        # 1, 2, 3, ... per team — a plain sequence rather than a timestamp, so "which
        # came first" never depends on clock resolution.
        sa.Column("version", sa.Integer(), nullable=False),
        # Agents (role, prompt, wytyczne, model_id, tools), edges (from, to), and the
        # run/day cost limits — everything specs/teams-catalogue and specs/teams-usage
        # require a saved revision to carry, as one immutable blob.
        sa.Column("definition", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("team_id", "version", name="team_revisions_team_version_unique"),
        sa.CheckConstraint("version >= 1", name="team_revisions_version_positive"),
    )
    # The one read the catalogue's "open this team" needs: its revisions, newest first.
    op.create_index(
        "ix_team_revisions_team_version",
        "team_revisions",
        ["team_id", sa.text("version DESC")],
    )


def downgrade() -> None:
    op.drop_table("team_revisions")
    op.drop_table("teams")
