"""The two facts `tc-runtime` cannot know about this module.

Where its migrations live, and which advisory-lock key they take. Everything else that
used to sit in `db.py`, `migrate.py` and `schema_version.py` here is one copy in the
package now — these two are what made those files this module's rather than anybody's.
"""

from __future__ import annotations

from pathlib import Path

# `teams/` and `migrations/` are siblings — in the repository and in the image
# (`Dockerfile` copies both), so one expression locates it in both.
MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"

# Advisory locks are scoped to one database and this module has its own, so the value only
# has to be stable — it carries the module's port so a log line naming it says which module
# took it. `tests/test_migrate.py` asserts this number: agent takes 8030 from the same
# helper, and a collision between the two would be a start-up that hangs rather than fails.
MIGRATION_LOCK_KEY = 8050
