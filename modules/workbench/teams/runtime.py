"""The two facts `tc-runtime` cannot know about this module.

Where its migrations live, and which advisory-lock key they take. Everything else that
used to sit in `db.py`, `migrate.py` and `schema_version.py` here is one copy in the
package now — these two are what made those files this module's rather than anybody's.
"""

from __future__ import annotations

from pathlib import Path

# `teams/` and `migrations/` are siblings — in the repository and in the image
# (`Dockerfile` copies both), so one expression locates it in both. The chain is named
# under `migrations/`, because the process runs a second one beside it.
MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations" / "teams"

# Advisory locks are scoped to one database and this surface has its own, so the value only
# has to be stable. It is the port this surface used to listen on, kept because a log line
# naming it still says which of the two chains took the lock. `tests/teams/test_migrate.py`
# asserts this number: the conversation's chain takes 8030 from the same helper, and the two
# run in one process now — a collision would be a start-up that hangs rather than fails.
MIGRATION_LOCK_KEY = 8050
