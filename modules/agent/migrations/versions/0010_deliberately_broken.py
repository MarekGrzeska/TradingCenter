"""A migration that fails on purpose, to prove a failed migration fails the deployment.

Task 6.4 of `modules-migrate-their-own-database`, and the only one of that change's
claims that cannot be checked by reading: that a broken migration produces a **red**
deployment rather than a green one over a dark module. That was the shape of the
16 August outage — `deploy-agent.yml` read the App Service control plane, saw
`state=Running`, and reported success while the container exited with code 3 on every
restart.

This is committed, deployed and reverted deliberately. It raises as its **first**
statement, before any DDL and before alembic writes `alembic_version`, so the production
database is left exactly where it was — the failure under test is the deployment's, not
the schema's.

`downgrade` is a no-op for the same reason: there is nothing to undo.

Revision ID: 0010
Revises: 0009
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    raise RuntimeError(
        "deliberately broken migration (task 6.4) — if you are reading this in a "
        "container log, the mechanism under test worked: the module refused to start "
        "and the deployment should have failed with it."
    )


def downgrade() -> None:
    pass
